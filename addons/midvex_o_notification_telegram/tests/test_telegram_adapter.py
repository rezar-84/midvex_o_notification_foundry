import io
import json
from urllib import error

from odoo.tests.common import TransactionCase

from ..controllers.telegram_webhook import chat_kind, secret_token_is_valid
from ..services import telegram_adapter as telegram_adapter_module
from ..services.telegram_adapter import TelegramAdapter


class FakeAccount:
    def __init__(self, api_key='TOKEN', webhook_secret=None, parse_mode=None):
        self.api_key = api_key
        self.webhook_secret = webhook_secret
        # Mirrors the real account: send() reads it to decide whether to ask
        # Telegram to parse markup.
        self.parse_mode = parse_mode


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


class TestTelegramCommandParsing(TransactionCase):
    """Command parsing was hard-coded to /link, so anything else fell through
    silently and looked identical to a delivery failure."""

    def setUp(self):
        super().setUp()
        self.parse = telegram_adapter_module.TelegramAdapter._parse_command

    def test_bare_command_is_recognised(self):
        self.assertEqual(self.parse('/status'), ('status', None))

    def test_command_with_argument_splits(self):
        self.assertEqual(self.parse('/link ABC12345'), ('link', 'ABC12345'))

    def test_bot_mention_suffix_is_stripped(self):
        """Telegram appends @botname to commands sent in a group; without
        stripping it every command breaks the moment the bot joins one."""
        self.assertEqual(self.parse('/status@vars_alerts_bot'), ('status', None))
        self.assertEqual(self.parse('/link@vars_alerts_bot ABC12345'), ('link', 'ABC12345'))

    def test_case_is_normalised(self):
        self.assertEqual(self.parse('/STATUS'), ('status', None))

    def test_unknown_command_is_not_claimed(self):
        self.assertEqual(self.parse('/deploy'), (None, None))

    def test_plain_text_is_not_a_command(self):
        self.assertEqual(self.parse('hello there'), (None, None))
        self.assertEqual(self.parse('ABC12345'), (None, None))


class TestRecipientCommandActions(TransactionCase):
    def setUp(self):
        super().setUp()
        channel = self.env['midvex.notification.channel'].search([('code', '=', 'telegram')], limit=1)
        self.account = self.env['midvex.notification.account'].create({
            'name': 'Test Bot', 'channel_id': channel.id, 'state': 'connected',
        })
        # A real active user, not env.user: in a test that is __system__, which
        # is active=False, and Odoo filters inactive records out of relational
        # reads - so an audience set to it reads back empty and the dispatcher
        # correctly finds nobody to notify.
        self.sales_user = self.env['res.users'].create({
            'name': 'Sales Tester', 'login': 'sales.tester@example.com',
        })
        self.recipient = self.env['midvex.notification.recipient'].create({
            'user_id': self.sales_user.id, 'account_id': self.account.id,
            'state': 'linked', 'external_id': '4242',
        })

    def test_find_linked_is_scoped_to_the_account(self):
        """The same chat can be linked to two bots; a command sent to one must
        not act on the other's link."""
        other_account = self.env['midvex.notification.account'].create({
            'name': 'Other Bot', 'channel_id': self.account.channel_id.id, 'state': 'connected',
        })
        Recipient = self.env['midvex.notification.recipient']
        self.assertEqual(Recipient.find_linked(self.account, '4242'), self.recipient)
        self.assertFalse(Recipient.find_linked(other_account, '4242'))
        self.assertFalse(Recipient.find_linked(self.account, '9999'))

    def test_mute_reports_whether_it_changed(self):
        self.assertTrue(self.recipient.action_set_muted(True))
        self.assertTrue(self.recipient.muted)
        self.assertFalse(self.recipient.action_set_muted(True))

    def test_unlink_revokes_and_drops_the_chat_id(self):
        """Revoked rather than deleted, and the external id is dropped so
        nothing can be sent to a chat that asked to be left alone."""
        self.recipient.action_unlink_chat()
        self.assertEqual(self.recipient.state, 'revoked')
        self.assertFalse(self.recipient.external_id)
        self.assertFalse(self.env['midvex.notification.recipient'].find_linked(self.account, '4242'))

    def test_muted_recipient_is_not_enqueued(self):
        """Muting must stop messages being created, not merely held - otherwise
        a backlog arrives the moment someone unmutes."""
        from odoo.addons.midvex_o_notification_foundry.services.dispatcher import enqueue_event
        template = self.env['midvex.notification.template'].create({
            'name': 'T', 'code': 'test_partner_created',
            'model_id': self.env['ir.model']._get_id('res.partner'),
            'body': 'New: {{ object.name }}',
        })
        rule = self.env['midvex.notification.rule'].create({
            'name': 'R', 'model_id': self.env['ir.model']._get_id('res.partner'),
            'trigger': 'on_create', 'template_id': template.id,
            'channel_ids': [(4, self.account.channel_id.id)],
            'audience_user_ids': [(4, self.sales_user.id)],
        })
        # Assert the preconditions the dispatcher looks for, so a failure says
        # which lookup came up empty rather than only that nothing was queued.
        self.assertTrue(rule.audience_user_ids, 'rule has no audience')
        self.assertEqual(self.recipient.channel_code, 'telegram')
        self.assertTrue(self.env['midvex.notification.account'].search([
            ('channel_code', '=', 'telegram'), ('state', '=', 'connected'),
            ('company_id', '=', self.env.company.id), ('active', '=', True),
        ]), 'no connected account matched')

        partner = self.env['res.partner'].create({'name': 'Alpha'})
        self.assertTrue(enqueue_event(self.env, 'res.partner', partner, 'created'),
                        'nothing queued while unmuted')

        self.recipient.action_set_muted(True)
        partner2 = self.env['res.partner'].create({'name': 'Beta'})
        self.assertFalse(enqueue_event(self.env, 'res.partner', partner2, 'created'))


class TestChatKind(TransactionCase):
    """Telegram tells us where a message came from; the link flow refuses a
    code redeemed in the wrong kind of chat on the strength of it."""

    def test_a_direct_message_is_a_user_chat(self):
        self.assertEqual(chat_kind({'chat_type': 'private'}), 'user')

    def test_groups_and_supergroups_are_both_rooms(self):
        self.assertEqual(chat_kind({'chat_type': 'group'}), 'group')
        self.assertEqual(chat_kind({'chat_type': 'supergroup'}), 'group')

    def test_an_unknown_or_missing_type_is_treated_as_a_dm(self):
        """The conservative reading: a personal code is refused in a chat we
        cannot identify rather than granted to it."""
        self.assertEqual(chat_kind({}), 'user')
        self.assertEqual(chat_kind({'chat_type': 'channel'}), 'user')


class TestParseInboundChatContext(TransactionCase):
    def setUp(self):
        super().setUp()
        self.adapter = TelegramAdapter()

    def test_group_message_carries_type_and_title(self):
        event = self.adapter.parse_inbound({'message': {
            'chat': {'id': -100999, 'type': 'supergroup', 'title': 'Sales room'},
            'from': {'username': 'jane'}, 'text': '/link ABC12345'}})
        self.assertEqual(event['external_id'], '-100999')
        self.assertEqual(event['chat_type'], 'supergroup')
        self.assertEqual(event['chat_title'], 'Sales room')

    def test_direct_message_has_no_title(self):
        event = self.adapter.parse_inbound({'message': {
            'chat': {'id': 555, 'type': 'private'}, 'from': {}, 'text': '/status'}})
        self.assertEqual(event['chat_type'], 'private')
        self.assertIsNone(event['chat_title'])


class TestGroupLinkCodes(TransactionCase):
    def setUp(self):
        super().setUp()
        channel = self.env['midvex.notification.channel'].search([('code', '=', 'telegram')], limit=1)
        self.account = self.env['midvex.notification.account'].create({
            'name': 'Test Bot', 'channel_id': channel.id, 'state': 'connected',
        })
        # A group chat has no user_id, so _check_self_or_manager can never see
        # it as "your own link" and always demands the manager group. That is
        # the intended rule - a shared room is not one person's to manage - so
        # the test takes the role a real admin already has.
        self.env.user.group_ids = [(4, self.env.ref(
            'midvex_o_notification_foundry.group_notification_manager').id)]
        self.Recipient = self.env['midvex.notification.recipient']

    def _pending(self, **values):
        recipient = self.Recipient.create(dict({'account_id': self.account.id}, **values))
        recipient.action_generate_link_code()
        return recipient

    def test_find_pending_by_code_does_not_redeem_it(self):
        """The lookup has to be side-effect free, or checking which kind of
        chat a code belongs to would consume it."""
        room = self._pending(kind='group', name='Sales room')
        found = self.Recipient.find_pending_by_code(room.link_code)
        self.assertEqual(found, room)
        self.assertEqual(room.state, 'pending')
        self.assertTrue(room.link_code)

    def test_expired_code_is_not_found(self):
        room = self._pending(kind='group', name='Sales room')
        room.write({'link_code_expires_at': '2020-01-01 00:00:00'})
        self.assertFalse(self.Recipient.find_pending_by_code(room.link_code))

    def test_linking_a_room_fills_a_blank_name_from_the_chat_title(self):
        room = self._pending(kind='group')
        self.Recipient.process_link_code(room.link_code, '-100999', 'jane', 'Sales room')
        self.assertEqual(room.state, 'linked')
        self.assertEqual(room.name, 'Sales room')

    def test_an_existing_name_survives_linking(self):
        room = self._pending(kind='group', name='Our name for it')
        self.Recipient.process_link_code(room.link_code, '-100999', 'jane', 'Telegram title')
        self.assertEqual(room.name, 'Our name for it')
