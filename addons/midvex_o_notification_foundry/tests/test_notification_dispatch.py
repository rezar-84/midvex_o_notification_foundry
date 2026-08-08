from odoo.exceptions import ValidationError
from odoo.tests.common import TransactionCase

from ..services import registry
from .common import ensure_channel


class MockAdapter:
    channel_code = 'notification_mock'

    def __init__(self):
        self.send_calls = []

    def test_connection(self, account):
        return {'ok': True}

    def send(self, account, message_dto):
        self.send_calls.append(message_dto)
        return {'ok': True, 'provider_message_id': 'mock-%s' % len(self.send_calls)}

    def register_webhook(self, account, webhook_url, secret_token):
        return {'ok': True}

    def parse_inbound(self, raw_payload):
        return {}

    def parse_error(self, response_or_exception):
        return {'error_code': 'UNKNOWN', 'message': str(response_or_exception), 'retryable': False}


class TestNotificationDispatchMocked(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.adapter = MockAdapter()
        registry._ADAPTERS[cls.adapter.channel_code] = cls.adapter
        cls.channel = ensure_channel(cls.env, cls.adapter.channel_code, 'Mock Channel')
        cls.account = cls.env['midvex.notification.account'].create({
            'name': 'Mock account', 'channel_id': cls.channel.id, 'state': 'connected',
        })
        # TransactionCase's default env.user is the inactive system user; Many2many reads to
        # res.users apply an implicit active_test filter, so a dedicated active user is needed
        # as the audience member here rather than cls.env.user.
        cls.member = cls.env['res.users'].create({
            'name': 'Dispatch Member', 'login': 'notif_dispatch_member', 'email': 'dispatch@example.com',
        })
        cls.recipient = cls.env['midvex.notification.recipient'].create({
            'user_id': cls.member.id, 'account_id': cls.account.id,
            'state': 'linked', 'external_id': 'chat-1',
        })
        partner_model = cls.env['ir.model']._get('res.partner')
        cls.template = cls.env['midvex.notification.template'].create({
            'name': 'Partner created', 'code': 'partner_created', 'model_id': partner_model.id,
            'subject': 'New partner', 'body': '{{ object.name }} was created',
        })
        cls.rule = cls.env['midvex.notification.rule'].create({
            'name': 'Notify on partner creation', 'model_id': partner_model.id, 'trigger': 'on_create',
            'template_id': cls.template.id, 'channel_ids': [(4, cls.channel.id)],
            'audience_user_ids': [(4, cls.member.id)],
        })

    @classmethod
    def tearDownClass(cls):
        registry.unregister_adapter(cls.adapter.channel_code)
        super().tearDownClass()

    def test_event_enqueues_and_processes_a_message(self):
        partner = self.env['res.partner'].create({'name': 'Acme Corp'})
        Message = self.env['midvex.notification.message']
        created = Message._trigger_event('res.partner', partner, 'created')
        self.assertEqual(len(created), 1)
        self.assertEqual(created.body, 'Acme Corp was created')
        self.assertEqual(created.state, 'pending')

        created.action_process()
        self.assertEqual(created.state, 'sent')
        self.assertEqual(len(self.adapter.send_calls), 1)
        self.assertEqual(self.adapter.send_calls[0]['recipient_external_id'], 'chat-1')

        log = self.env['midvex.notification.log'].search([('message_id', '=', created.id)])
        self.assertEqual(log.status, 'success')

    def test_duplicate_trigger_does_not_create_a_second_message(self):
        partner = self.env['res.partner'].create({'name': 'Beta LLC'})
        Message = self.env['midvex.notification.message']
        first = Message._trigger_event('res.partner', partner, 'created')
        second = Message._trigger_event('res.partner', partner, 'created')
        self.assertEqual(len(second), 0)
        messages = Message.search([('res_model', '=', 'res.partner'), ('res_id', '=', partner.id)])
        self.assertEqual(len(messages), 1)
        self.assertEqual(messages, first)

    def test_unlinked_recipient_is_skipped(self):
        self.recipient.write({'state': 'pending'})
        partner = self.env['res.partner'].create({'name': 'Gamma Inc'})
        created = self.env['midvex.notification.message']._trigger_event('res.partner', partner, 'created')
        self.assertEqual(len(created), 0)
        self.recipient.write({'state': 'linked'})


class TestGroupChatRecipients(TransactionCase):
    """A shared chat is a destination in its own right, not somebody's link."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.adapter = MockAdapter()
        registry._ADAPTERS[cls.adapter.channel_code] = cls.adapter
        cls.channel = ensure_channel(cls.env, cls.adapter.channel_code, 'Mock Channel')
        cls.account = cls.env['midvex.notification.account'].create({
            'name': 'Group account', 'channel_id': cls.channel.id, 'state': 'connected',
        })
        cls.room = cls.env['midvex.notification.recipient'].create({
            'kind': 'group', 'name': 'Sales room', 'account_id': cls.account.id,
            'state': 'linked', 'external_id': '-100999',
        })
        partner_model = cls.env['ir.model']._get('res.partner')
        cls.template = cls.env['midvex.notification.template'].create({
            'name': 'Partner created', 'code': 'group_partner_created',
            'model_id': partner_model.id, 'body': '{{ object.name }} was created',
        })
        cls.rule = cls.env['midvex.notification.rule'].create({
            'name': 'Notify the sales room', 'model_id': partner_model.id,
            'trigger': 'on_create', 'template_id': cls.template.id,
            'channel_ids': [(4, cls.channel.id)],
            'audience_recipient_ids': [(4, cls.room.id)],
        })

    @classmethod
    def tearDownClass(cls):
        registry.unregister_adapter(cls.adapter.channel_code)
        super().tearDownClass()

    def test_a_group_chat_needs_no_user(self):
        self.assertFalse(self.room.user_id)
        self.assertEqual(self.room.display_name, 'Sales room')

    def test_a_group_chat_may_not_carry_a_user(self):
        """The dispatcher resolves user recipients by user_id, so a group chat
        holding one would receive that person's private alerts."""
        user = self.env['res.users'].create({'name': 'Nina', 'login': 'group_nina'})
        with self.assertRaises(ValidationError):
            self.room.write({'user_id': user.id})

    def test_a_user_recipient_still_needs_a_user(self):
        with self.assertRaises(ValidationError):
            self.env['midvex.notification.recipient'].create({
                'kind': 'user', 'account_id': self.account.id,
            })

    def test_one_account_serves_several_rooms(self):
        """UNIQUE (account_id, user_id) must not collapse group chats onto one
        row: Postgres treats NULLs as distinct, and we rely on that."""
        second = self.env['midvex.notification.recipient'].create({
            'kind': 'group', 'name': 'Ops room', 'account_id': self.account.id,
            'state': 'linked', 'external_id': '-100888',
        })
        self.assertNotEqual(second, self.room)

    def test_rule_delivers_to_the_room(self):
        partner = self.env['res.partner'].create({'name': 'Delta Ltd'})
        created = self.env['midvex.notification.message']._trigger_event(
            'res.partner', partner, 'created')
        self.assertEqual(len(created), 1)
        self.assertEqual(created.recipient_id, self.room)
        self.assertEqual(created.body, 'Delta Ltd was created')

    def test_a_muted_room_is_not_enqueued(self):
        self.room.action_set_muted(True)
        partner = self.env['res.partner'].create({'name': 'Epsilon Ltd'})
        created = self.env['midvex.notification.message']._trigger_event(
            'res.partner', partner, 'created')
        self.assertEqual(len(created), 0)
        self.room.action_set_muted(False)

    def test_an_archived_room_is_not_enqueued(self):
        """Archiving is the off switch: Odoo drops inactive records from
        relational reads, so the rule stops seeing it."""
        self.room.write({'active': False})
        partner = self.env['res.partner'].create({'name': 'Zeta Ltd'})
        created = self.env['midvex.notification.message']._trigger_event(
            'res.partner', partner, 'created')
        self.assertEqual(len(created), 0)
        self.room.write({'active': True})

    def test_a_room_and_a_user_both_get_their_own_message(self):
        """Their idempotency keys must not collide, or whichever is enqueued
        second is silently swallowed as a duplicate."""
        member = self.env['res.users'].create({'name': 'Omar', 'login': 'group_omar'})
        self.env['midvex.notification.recipient'].create({
            'user_id': member.id, 'account_id': self.account.id,
            'state': 'linked', 'external_id': 'chat-omar',
        })
        self.rule.write({'audience_user_ids': [(4, member.id)]})
        partner = self.env['res.partner'].create({'name': 'Theta Ltd'})
        created = self.env['midvex.notification.message']._trigger_event(
            'res.partner', partner, 'created')
        self.assertEqual(len(created), 2)
        self.assertEqual(len(created.mapped('idempotency_key')), 2)
