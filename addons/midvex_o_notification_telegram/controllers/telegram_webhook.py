import logging

from odoo import _, fields
from odoo.http import Controller, request, route

from odoo.addons.midvex_o_notification_foundry.services.registry import get_adapter

_logger = logging.getLogger(__name__)

def secret_token_is_valid(account, header_value):
    """Verify Telegram's X-Telegram-Bot-Api-Secret-Token webhook header against the account secret."""
    if not account.webhook_secret:
        return True
    return header_value == account.webhook_secret


class TelegramWebhookController(Controller):

    @staticmethod
    def _help_text():
        # Built here rather than at module level: _() resolves against the
        # environment's language, which does not exist at import time.
        return _(
            "VARS notifications bot\n\n"
            "/link <code> - connect this chat to your Odoo user\n"
            "/status - show whether this chat is connected\n"
            "/mute - pause alerts, keeping the connection\n"
            "/unmute - resume alerts\n"
            "/unlink - disconnect this chat\n"
            "/help - show this message\n\n"
            "Generate a link code from your Recipient record in Odoo. Codes expire "
            "after 15 minutes."
        )

    def _handle_command(self, env, account, event):
        """Run an inbound command and return (recipient, error, reply_text).

        Every branch returns something to say back. Before this the bot was
        silent on every command including /link, so a person who linked
        successfully saw exactly the same thing as one whose code had expired:
        nothing at all.
        """
        command = event.get('command')
        external_id = event.get('external_id')
        Recipient = env['midvex.notification.recipient']

        if command in ('start', 'help'):
            return False, False, HELP_TEXT

        if command == 'link':
            code = event.get('command_args')
            if not code:
                return False, False, _("Send the code with the command, like: /link ABC12345")
            recipient = Recipient.sudo().process_link_code(
                code, external_id, event.get('external_username'))
            if not recipient:
                return False, 'Link code was invalid, already used, or expired.', _(
                    "That code was not accepted. It may have expired (codes last 15 "
                    "minutes), already been used, or been typed differently - they are "
                    "case-sensitive. Generate a fresh one in Odoo and try again."
                )
            return recipient, False, _(
                "Connected. Alerts for %s will arrive here.", recipient.user_id.name)

        recipient = Recipient.find_linked(account, external_id)
        if not recipient:
            return False, False, _(
                "This chat is not connected to an Odoo user. Use /link <code> to "
                "connect it.")

        if command == 'status':
            state = _("muted") if recipient.muted else _("active")
            return recipient, False, _(
                "Connected as %(user)s. Alerts are %(state)s.",
                user=recipient.user_id.name, state=state)

        if command == 'mute':
            changed = recipient.action_set_muted(True)
            return recipient, False, (
                _("Alerts paused. Send /unmute to resume.") if changed
                else _("Alerts were already paused."))

        if command == 'unmute':
            changed = recipient.action_set_muted(False)
            return recipient, False, (
                _("Alerts resumed.") if changed else _("Alerts were already active."))

        if command == 'unlink':
            user_name = recipient.user_id.name
            recipient.action_unlink_chat()
            return recipient, False, _(
                "Disconnected. %s will no longer receive alerts here. Use /link with a "
                "new code to reconnect.", user_name)

        return False, False, None

    @route(['/notification/telegram/webhook/<int:account_id>'], type='http', auth='public',
           methods=['POST'], csrf=False, save_session=False)
    def telegram_webhook(self, account_id, **kwargs):
        env = request.env
        account = env['midvex.notification.account'].sudo().browse(account_id).exists()
        if not account or account.channel_code != 'telegram':
            return request.make_json_response({'status': 'error'}, status=404)

        secret_header = request.httprequest.headers.get('X-Telegram-Bot-Api-Secret-Token')
        if not secret_token_is_valid(account, secret_header):
            return request.make_json_response({'status': 'forbidden'}, status=403)

        try:
            raw_payload = request.get_json_data()
        except ValueError:
            return request.make_json_response({'status': 'error'}, status=400)

        adapter = get_adapter('telegram')
        event = adapter.parse_inbound(raw_payload or {})

        inbound = env['midvex.notification.inbound.event'].sudo().create({
            'channel_id': account.channel_id.id,
            'account_id': account.id,
            'event_type': event.get('command') or 'message',
            'external_id': event.get('external_id'),
            'raw_payload': raw_payload,
        })

        recipient = False
        error_message = False
        reply = None
        if event.get('command'):
            recipient, error_message, reply = self._handle_command(env, account, event)

        if reply:
            # Best effort. Telegram retries any non-200 response, so a failure
            # to reply must not fail the request or the same command would be
            # replayed and re-executed.
            try:
                adapter.send_text(account, event.get('external_id'), reply)
            except Exception:
                _logger.warning('Telegram reply failed for inbound event %s', inbound.id,
                                exc_info=True)

        inbound.write({
            'processed': True,
            'processed_at': fields.Datetime.now(),
            'recipient_id': recipient.id if recipient else False,
            'error_message': error_message,
        })

        return request.make_json_response({'status': 'ok'}, status=200)
