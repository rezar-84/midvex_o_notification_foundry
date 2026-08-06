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
