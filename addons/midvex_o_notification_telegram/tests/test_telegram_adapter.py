import io
import json
from urllib import error

from odoo.tests.common import TransactionCase

from ..controllers.telegram_webhook import secret_token_is_valid
from ..services import telegram_adapter as telegram_adapter_module
from ..services.telegram_adapter import TelegramAdapter


class FakeAccount:
    def __init__(self, api_key='TOKEN', webhook_secret=None):
        self.api_key = api_key
        self.webhook_secret = webhook_secret


class TestTelegramAdapter(TransactionCase):
    def setUp(self):
        super().setUp()
        self.adapter = TelegramAdapter()
        self.account = FakeAccount()

    def test_send_builds_chat_id_and_text(self):
        captured = {}

        def fake_request(account, api_method, payload=None):
            captured['api_method'] = api_method
            captured['payload'] = payload
            return {'ok': True, 'result': {'message_id': 42}}

        self.adapter._request = fake_request
        result = self.adapter.send(self.account, {'recipient_external_id': 'chat-1', 'body': 'Hello'})
        self.assertEqual(captured['api_method'], 'sendMessage')
        self.assertEqual(captured['payload'], {'chat_id': 'chat-1', 'text': 'Hello'})
        self.assertEqual(result['provider_message_id'], 42)
        self.assertEqual(result['status'], 'sent')

    def test_register_webhook_sends_url_and_secret(self):
        captured = {}

        def fake_request(account, api_method, payload=None):
            captured['api_method'] = api_method
            captured['payload'] = payload
            return {'ok': True}

        self.adapter._request = fake_request
        self.adapter.register_webhook(self.account, 'https://example.com/hook', 'sec-token')
        self.assertEqual(captured['api_method'], 'setWebhook')
        self.assertEqual(captured['payload'], {'url': 'https://example.com/hook', 'secret_token': 'sec-token'})

    def test_parse_inbound_extracts_link_command(self):
        raw = {'update_id': 1, 'message': {'chat': {'id': 555}, 'from': {'username': 'jane'}, 'text': '/link ABC123'}}
        event = self.adapter.parse_inbound(raw)
        self.assertEqual(event['external_id'], '555')
        self.assertEqual(event['external_username'], 'jane')
        self.assertEqual(event['command'], 'link')
        self.assertEqual(event['command_args'], 'ABC123')

    def test_parse_inbound_without_command(self):
        raw = {'update_id': 2, 'message': {'chat': {'id': 555}, 'from': {}, 'text': 'hello there'}}
        event = self.adapter.parse_inbound(raw)
        self.assertIsNone(event['command'])

    def test_rate_limit_error_is_surfaced_with_retry_after(self):
        def fake_urlopen(req, timeout=None):
            body = json.dumps({
                'ok': False, 'error_code': 429, 'description': 'Too Many Requests',
                'parameters': {'retry_after': 5},
            }).encode()
            raise error.HTTPError(req.full_url, 429, 'Too Many Requests', {}, io.BytesIO(body))

        original = telegram_adapter_module.request.urlopen
        telegram_adapter_module.request.urlopen = fake_urlopen
        try:
            with self.assertRaises(Exception) as ctx:
                self.adapter._request(FakeAccount(), 'sendMessage', {'chat_id': '1', 'text': 'hi'})
            self.assertIn('429', str(ctx.exception))
        finally:
            telegram_adapter_module.request.urlopen = original


class TestTelegramWebhookSecretVerification(TransactionCase):
    def test_no_secret_configured_accepts_any_header(self):
        self.assertTrue(secret_token_is_valid(FakeAccount(webhook_secret=None), None))

    def test_matching_secret_is_accepted(self):
        self.assertTrue(secret_token_is_valid(FakeAccount(webhook_secret='sec-token'), 'sec-token'))

    def test_mismatched_secret_is_rejected(self):
        self.assertFalse(secret_token_is_valid(FakeAccount(webhook_secret='sec-token'), 'wrong'))
        self.assertFalse(secret_token_is_valid(FakeAccount(webhook_secret='sec-token'), None))
