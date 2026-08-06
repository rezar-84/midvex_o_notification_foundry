import json
from urllib import error, request

from odoo.exceptions import UserError
from odoo.addons.midvex_o_notification_foundry.services.registry import register_adapter


@register_adapter
class TelegramAdapter:
    channel_code = 'telegram'
    timeout = 20

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

    def send(self, account, message_dto):
        if not message_dto.get('recipient_external_id'):
            raise UserError('Recipient has no linked Telegram chat id.')
        payload = {'chat_id': message_dto['recipient_external_id'], 'text': message_dto.get('body') or ''}
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

    def parse_inbound(self, raw_payload):
        message = raw_payload.get('message') or {}
        chat = message.get('chat') or {}
        sender = message.get('from') or {}
        text = message.get('text') or ''
        command = None
        command_args = None
        if text.startswith('/link'):
            parts = text.split(maxsplit=1)
            command = 'link'
            command_args = parts[1].strip() if len(parts) > 1 else None
        return {
            'external_id': str(chat['id']) if chat.get('id') is not None else None,
            'external_username': sender.get('username'),
            'text': text,
            'command': command,
            'command_args': command_args,
            'raw': raw_payload,
        }

    def parse_error(self, response_or_exception):
        return {'error_code': 'TELEGRAM_ERROR', 'message': str(response_or_exception), 'retryable': False}
