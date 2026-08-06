from odoo import fields
from odoo.http import Controller, request, route

from odoo.addons.midvex_o_notification_foundry.services.registry import get_adapter


def secret_token_is_valid(account, header_value):
    """Verify Telegram's X-Telegram-Bot-Api-Secret-Token webhook header against the account secret."""
    if not account.webhook_secret:
        return True
    return header_value == account.webhook_secret


class TelegramWebhookController(Controller):

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
        if event.get('command') == 'link' and event.get('command_args'):
            recipient = env['midvex.notification.recipient'].sudo().process_link_code(
                event['command_args'], event.get('external_id'), event.get('external_username'))
            if not recipient:
                error_message = 'Link code was invalid, already used, or expired.'

        inbound.write({
            'processed': True,
            'processed_at': fields.Datetime.now(),
            'recipient_id': recipient.id if recipient else False,
            'error_message': error_message,
        })

        return request.make_json_response({'status': 'ok'}, status=200)
