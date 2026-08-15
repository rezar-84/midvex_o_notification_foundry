from odoo.tests.common import TransactionCase

from odoo.addons.midvex_o_notification_foundry.services import registry
from odoo.addons.midvex_o_notification_foundry.tests.common import ensure_channel


class FakeChannelAdapter:
    """A channel that exists only in memory.

    The conversation foundry is provider-neutral, and the tests have to be too:
    proving it against WhatsApp would prove the WhatsApp module. This adapter
    records what it was asked to send and answers with a plausible provider id.
    """

    channel_code = 'conversation_fake'
    # No rate limits declared, so the throttle stays out of the way of tests
    # that are about conversations rather than about pacing.

    def __init__(self):
        self.send_calls = []
        self.failure = None

    def test_connection(self, account):
        return {'ok': True, 'name': 'Fake Channel'}

    def send(self, account, message_dto):
        if self.failure:
            raise self.failure
        self.send_calls.append(message_dto)
        return {'provider_message_id': 'fake-%s' % len(self.send_calls),
                'status': 'sent', 'raw': {}}

    def register_webhook(self, account, webhook_url, secret_token):
        return {'ok': True}

    def parse_inbound(self, raw_payload):
        return {}

    def parse_error(self, response_or_exception):
        return {
            'error_code': 'FAKE_ERROR',
            'message': str(response_or_exception),
            'retryable': getattr(response_or_exception, 'is_retryable', True),
            'retry_after_seconds': None,
        }


class ConversationCase(TransactionCase):
    """Two companies, each with an account, so isolation is testable throughout."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.adapter = FakeChannelAdapter()
        registry._ADAPTERS[cls.adapter.channel_code] = cls.adapter
        cls.channel = ensure_channel(cls.env, cls.adapter.channel_code, 'Fake Channel')

        cls.company_a = cls.env['res.company'].create({'name': 'Conversation Co A'})
        cls.company_b = cls.env['res.company'].create({'name': 'Conversation Co B'})
        cls.account_a = cls.env['midvex.notification.account'].create({
            'name': 'Account A', 'channel_id': cls.channel.id,
            'company_id': cls.company_a.id, 'state': 'connected',
        })
        cls.account_b = cls.env['midvex.notification.account'].create({
            'name': 'Account B', 'channel_id': cls.channel.id,
            'company_id': cls.company_b.id, 'state': 'connected',
        })
        cls.Thread = cls.env['midvex.conversation.thread']
        cls.Session = cls.env['midvex.conversation.session']
        cls.Message = cls.env['midvex.conversation.message']
        cls.Identity = cls.env['midvex.conversation.identity']

    @classmethod
    def tearDownClass(cls):
        registry.unregister_adapter(cls.adapter.channel_code)
        super().tearDownClass()

    def setUp(self):
        super().setUp()
        # The adapter is one Python object for the whole class, and nothing
        # rolls its call log back the way the database is rolled back. The
        # 2026-08-09 handoff learned this the hard way; it applies to anything
        # hung off a registered adapter.
        self.adapter.send_calls = []
        self.adapter.failure = None

    # --- fixtures ------------------------------------------------------

    def identity(self, company=None, identifier='+905111111111'):
        from odoo.addons.midvex_o_conversation_foundry.services import conversation
        return conversation.ensure_identity(
            self.env, company or self.company_a, 'whatsapp', identifier)

    def thread(self, company=None, identity=None):
        from odoo.addons.midvex_o_conversation_foundry.services import conversation
        company = company or self.company_a
        return conversation.ensure_thread(
            self.env, company, identity or self.identity(company))

    def session(self, thread=None, account=None, address='+905111111111'):
        from odoo.addons.midvex_o_conversation_foundry.services import conversation
        thread = thread or self.thread()
        return conversation.open_session(
            self.env, thread, account or self.account_a, address)
