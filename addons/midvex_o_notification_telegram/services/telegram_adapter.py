import json
from urllib import error, request

from odoo.exceptions import UserError
from odoo.addons.midvex_o_notification_foundry.services.registry import register_adapter


@register_adapter
class TelegramAdapter:
    channel_code = 'telegram'
    timeout = 20

    # Telegram's published limits, verified 2026-08-10 at
    # https://core.telegram.org/bots/faq — see docs/projects/notification_telegram/
    # API_RESEARCH.md. They live here rather than in the foundry because the
    # foundry must not know anything channel-specific, and because the numbers
    # belong next to the research that justifies them.
    #
    # "We may allow short bursts that go over this limit, but eventually you'll
    # begin receiving 429 errors", so these are the sustained rates to stay
    # under, not hard walls. The group figure is the one that bites first: a
    # rule pointed at a busy shared room can breach it from a single batch.
    rate_limit_chat_seconds = 1        # one message per second to one chat
    rate_limit_group_per_minute = 20   # twenty per minute in a group
    rate_limit_global_per_second = 30  # about thirty per second overall

    def _url(self, account, api_method):
        if not account.api_key:
            raise UserError('Telegram bot token is not configured.')
        return f'https://api.telegram.org/bot{account.api_key}/{api_method}'

    def _request(self, account, api_method, payload=None):
        data = json.dumps(payload).encode() if payload is not None else None
        headers = {'Content-Type': 'application/json'} if data else {}
        req = request.Request(self._url(account, api_method), data=data, headers=headers)
        try:
            with request.urlopen(req, timeout=self.timeout) as response:
                return json.loads(response.read().decode() or '{}')
        except error.HTTPError as exc:
            try:
                body = json.loads(exc.read().decode() or '{}')
            except ValueError:
                body = {}
            description = body.get('description') or 'HTTP %s' % exc.code
            if exc.code == 429:
                retry_after = (body.get('parameters') or {}).get('retry_after', 30)
                raise UserError('Telegram rate limit reached (429): %s. Retry after %ss.' % (description, retry_after)) from exc
            raise UserError('Telegram API request failed: %s' % description) from exc
        except error.URLError as exc:
            raise UserError('Telegram API connection failed.') from exc

    def test_connection(self, account):
        result = self._request(account, 'getMe')
        if not result.get('ok'):
            raise UserError('Telegram getMe did not return ok=true.')
        return result.get('result')

    def _record_button(self, account, message_dto):
        """An "Open in Odoo" button on the message, when we know the record.

        /mail/view is used rather than a backend URL built by hand: it is
        model-agnostic and redirects to whatever form view applies, so this
        keeps working for rules on models other than crm.lead.

        Only offered over https — Telegram rejects a button whose URL it
        cannot reach, which would fail the whole send on a dev instance whose
        base URL is still localhost.
        """
        model, res_id = message_dto.get('res_model'), message_dto.get('res_id')
        if not model or not res_id:
            return None
        base_url = account.env['ir.config_parameter'].sudo().get_param('web.base.url') or ''
        if not base_url.startswith('https://'):
            return None
        url = f'{base_url}/mail/view?model={model}&res_id={res_id}'
        return {'inline_keyboard': [[{'text': 'Open in Odoo', 'url': url}]]}

    def send(self, account, message_dto):
        if not message_dto.get('recipient_external_id'):
            raise UserError('Recipient has no linked Telegram chat id.')
        payload = {'chat_id': message_dto['recipient_external_id'], 'text': message_dto.get('body') or ''}
        # Absent on the account means plain text, which is how every message
        # behaved before the field existed.
        if account.parse_mode:
            payload['parse_mode'] = account.parse_mode
        button = self._record_button(account, message_dto)
        if button:
            payload['reply_markup'] = button
        result = self._request(account, 'sendMessage', payload)
        if not result.get('ok'):
            raise UserError('Telegram sendMessage failed: %s' % result.get('description'))
        message = result.get('result') or {}
        return {'provider_message_id': message.get('message_id'), 'status': 'sent', 'raw': message}

    def register_webhook(self, account, webhook_url, secret_token):
        payload = {'url': webhook_url}
        if secret_token:
            payload['secret_token'] = secret_token
        result = self._request(account, 'setWebhook', payload)
        if not result.get('ok'):
            raise UserError('Telegram setWebhook failed: %s' % result.get('description'))
        return result

    #: Commands the webhook answers. Anything else is stored as a plain message
    #: and ignored, so an unknown command never silently looks like a failure.
    COMMANDS = ('start', 'help', 'link', 'status', 'unlink', 'mute', 'unmute')

    @classmethod
    def _parse_command(cls, text):
        """Split "/status" or "/link ABC123" into (command, args).

        Telegram appends the bot's username to commands sent in a group
        ("/status@vars_bot"), so that suffix is stripped — otherwise every
        command would be unrecognised the moment the bot joined a group.
        """
        if not text.startswith('/'):
            return None, None
        parts = text.split(maxsplit=1)
        command = parts[0][1:].split('@', 1)[0].strip().lower()
        if command not in cls.COMMANDS:
            return None, None
        return command, parts[1].strip() if len(parts) > 1 else None

    def send_text(self, account, chat_id, text):
        """Send a plain reply to a chat, outside the queued-message pipeline.

        Used for command responses, which are conversational rather than
        notifications: they have no rule, no template and nothing to retry.
        """
        if not chat_id or not text:
            return None
        return self._request(account, 'sendMessage', {'chat_id': chat_id, 'text': text})

    def parse_inbound(self, raw_payload):
        message = raw_payload.get('message') or {}
        chat = message.get('chat') or {}
        sender = message.get('from') or {}
        text = message.get('text') or ''
        command, command_args = self._parse_command(text)
        return {
            'external_id': str(chat['id']) if chat.get('id') is not None else None,
            'external_username': sender.get('username'),
            # 'private' for a DM, 'group'/'supergroup' for a room. Used to
            # refuse a link code redeemed in the wrong kind of chat, so one
            # person's link cannot quietly become a whole room's.
            'chat_type': chat.get('type'),
            'chat_title': chat.get('title'),
            'text': text,
            'command': command,
            'command_args': command_args,
            'raw': raw_payload,
        }

    def parse_error(self, response_or_exception):
        return {'error_code': 'TELEGRAM_ERROR', 'message': str(response_or_exception), 'retryable': False}
