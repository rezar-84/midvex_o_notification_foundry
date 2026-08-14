import io
import json
from urllib import error

from odoo.exceptions import UserError
from odoo.tests.common import TransactionCase

from . import fixtures
from ..services import whatsapp_client as whatsapp_client_module
from ..services.whatsapp_adapter import WhatsAppAdapter
from ..services.whatsapp_client import WhatsAppClient, WhatsAppError


class FakeAccount:
    """Enough of midvex.notification.account for the client and adapter.

    A real record would drag in a database and the admin group that gates
    api_key, for tests that are about payload shapes and error classification.
    The model-level tests below use real records where that matters.
    """

    def __init__(self, api_key='TOKEN-PLACEHOLDER', phone_number_id=fixtures.PHONE_NUMBER_ID,
                 api_version=None):
        self.api_key = api_key
        self.wa_phone_number_id = phone_number_id
        self.wa_api_version = api_version
        self.wa_business_account_id = fixtures.WABA_ID

    def sudo(self):
        return self


def http_error(status, body):
    return error.HTTPError(
        'https://graph.facebook.com/', status, 'error', {},
        io.BytesIO(json.dumps(body).encode()))


class TestWhatsAppClient(TransactionCase):
    def setUp(self):
        super().setUp()
        self.client = WhatsAppClient()
        self.account = FakeAccount()

    def test_url_pins_the_default_api_version(self):
        self.assertEqual(
            self.client._url(self.account, 'x'),
            'https://graph.facebook.com/%s/x' % whatsapp_client_module.DEFAULT_API_VERSION)

    def test_account_overrides_the_api_version(self):
        account = FakeAccount(api_version='v26.0')
        self.assertEqual(self.client._url(account, 'x'), 'https://graph.facebook.com/v26.0/x')

    def test_missing_token_is_refused_before_any_request(self):
        with self.assertRaises(WhatsAppError) as caught:
            self.client.request(FakeAccount(api_key=False), 'x')
        # The flag is the point: it is what stops the queue retrying a record
        # that no retry can fix.
        self.assertTrue(caught.exception.permanent)

    def test_missing_phone_number_id_is_refused_before_any_request(self):
        with self.assertRaises(WhatsAppError) as caught:
            self.client.send_message(FakeAccount(phone_number_id=False), {})
        self.assertTrue(caught.exception.permanent)

    def test_http_error_carries_the_provider_code_and_trace(self):
        raised = self.client._error_from_http(http_error(400, fixtures.error_body(131047)))
        self.assertEqual(raised.code, 131047)
        self.assertEqual(raised.http_status, 400)
        self.assertEqual(raised.fbtrace_id, 'trace-placeholder')

    def test_http_error_prefers_details_over_the_generic_message(self):
        raised = self.client._error_from_http(
            http_error(400, fixtures.error_body(132001, details='Template not found')))
        self.assertIn('Template not found', str(raised))
        self.assertNotIn('Unsupported post request', str(raised))

    def test_unreadable_error_body_still_produces_an_error(self):
        broken = error.HTTPError('https://graph.facebook.com/', 500, 'error', {},
                                 io.BytesIO(b'<html>not json</html>'))
        raised = self.client._error_from_http(broken)
        self.assertEqual(raised.http_status, 500)
        self.assertIsNone(raised.code)


class TestWhatsAppSend(TransactionCase):
    def setUp(self):
        super().setUp()
        self.adapter = WhatsAppAdapter()
        self.account = FakeAccount()
        self.sent = []

        def fake_send(account, payload):
            self.sent.append(payload)
            return fixtures.send_success()

        self.adapter.client.send_message = fake_send
        # No template mapping unless a test asks for one. The real lookup needs
        # a database record; these tests are about payload shape.
        self.adapter._resolve_template = lambda account, dto: None

    def test_text_payload_shape(self):
        result = self.adapter.send(
            self.account, {'recipient_external_id': '+905111111111', 'body': 'Hello'})
        self.assertEqual(self.sent[0], {
            'messaging_product': 'whatsapp',
            'recipient_type': 'individual',
            'to': '+905111111111',
            'type': 'text',
            'text': {'preview_url': False, 'body': 'Hello'},
        })
        self.assertEqual(result['provider_message_id'], fixtures.OUTBOUND_WAMID)
        self.assertEqual(result['status'], 'sent')

    def test_template_payload_shape(self):
        self.adapter._resolve_template = lambda account, dto: {
            'name': 'vars_lead_created',
            'language': {'code': 'tr_TR'},
            'components': [{'type': 'body', 'parameters': [{'type': 'text', 'text': 'Acme'}]}],
        }
        self.adapter.send(self.account, {'recipient_external_id': '+905111111111',
                                          'body': 'ignored', 'template_code': 'lead_created'})
        self.assertEqual(self.sent[0]['type'], 'template')
        self.assertEqual(self.sent[0]['template']['name'], 'vars_lead_created')
        self.assertNotIn('text', self.sent[0])

    def test_send_without_a_recipient_is_refused(self):
        with self.assertRaises(WhatsAppError) as caught:
            self.adapter.send(self.account, {'body': 'Hello'})
        self.assertTrue(caught.exception.permanent)

    def test_accepted_response_without_a_wamid_is_a_failure(self):
        """A 200 carrying no message id has not sent anything.

        Treating it as sent would leave a row marked delivered that no status
        webhook will ever mention again — invisible, and indistinguishable from
        a message the customer simply ignored.
        """
        self.adapter.client.send_message = lambda account, payload: {'messages': []}
        with self.assertRaises(UserError):
            self.adapter.send(self.account, {'recipient_external_id': '+905111111111',
                                              'body': 'Hello'})


class TestWhatsAppTestConnection(TransactionCase):
    def setUp(self):
        super().setUp()
        self.adapter = WhatsAppAdapter()
        self.account = FakeAccount()

    def test_reads_the_phone_number_node(self):
        self.adapter.client.get_phone_number = lambda account: {
            'id': fixtures.PHONE_NUMBER_ID,
            'display_phone_number': '+90 500 000 0000',
            'verified_name': 'VARS',
            'quality_rating': 'GREEN',
        }
        info = self.adapter.test_connection(self.account)
        # action_test_connection displays 'name' or 'username'.
        self.assertEqual(info['name'], 'VARS')
        self.assertEqual(info['quality_rating'], 'GREEN')

    def test_a_response_without_an_id_is_not_a_successful_connection(self):
        self.adapter.client.get_phone_number = lambda account: {}
        with self.assertRaises(UserError):
            self.adapter.test_connection(self.account)

    def test_register_webhook_refuses_rather_than_pretending(self):
        """Meta has no setWebhook, and a button that silently succeeds is worse
        than one that explains why it cannot."""
        with self.assertRaises(UserError):
            self.adapter.register_webhook(self.account, 'https://example.com/hook', 'tok')


class TestWhatsAppErrorClassification(TransactionCase):
    def setUp(self):
        super().setUp()
        self.adapter = WhatsAppAdapter()

    def verdict(self, code=None, http_status=400, retry_after=None):
        return self.adapter.parse_error(WhatsAppError(
            'boom', code=code, http_status=http_status, retry_after=retry_after))

    def test_rate_limit_defers_and_is_retryable(self):
        for code in (4, 80007, 130429, 131056):
            with self.subTest(code=code):
                verdict = self.verdict(code)
                self.assertEqual(verdict['error_code'], 'WHATSAPP_RATE_LIMIT')
                self.assertTrue(verdict['retryable'])
                # A retry_after is what makes _handle_failure give back the
                # attempt instead of counting it. Without one, a rate limit
                # would burn a try — the ADR-012 bug, in a new channel.
                self.assertTrue(verdict['retry_after_seconds'])

    def test_rate_limit_uses_the_providers_own_delay_when_given(self):
        self.assertEqual(self.verdict(130429, retry_after=90)['retry_after_seconds'], 90)

    def test_http_429_without_a_known_code_is_still_a_rate_limit(self):
        self.assertEqual(self.verdict(None, http_status=429)['error_code'],
                         'WHATSAPP_RATE_LIMIT')

    def test_authentication_is_permanent(self):
        for code in (0, 190, 200):
            with self.subTest(code=code):
                verdict = self.verdict(code)
                self.assertEqual(verdict['error_code'], 'WHATSAPP_AUTH')
                self.assertFalse(verdict['retryable'])

    def test_closed_messaging_window_is_permanent(self):
        """131047 means 24 hours passed since the customer last replied.

        Retrying cannot help; only an approved template can. Classifying it
        retryable would burn all three attempts and then look like a network
        problem in the queue.
        """
        verdict = self.verdict(131047)
        self.assertEqual(verdict['error_code'], 'WHATSAPP_POLICY_RESTRICTED')
        self.assertFalse(verdict['retryable'])

    def test_template_and_recipient_problems_are_permanent(self):
        self.assertFalse(self.verdict(132001)['retryable'])
        self.assertFalse(self.verdict(131026)['retryable'])

    def test_a_misconfigured_record_is_permanent_not_retried(self):
        """No token, no phone number ID, no recipient — the record is wrong.

        Left to the generic path these retry three times over half an hour and
        then report "failed", indistinguishable from a provider outage, when
        what they need is a human. Quarantining says that plainly and says it
        immediately.
        """
        for message in ('WhatsApp access token is not configured on this account.',
                        'WhatsApp phone number ID is not configured on this account.',
                        'Recipient has no linked WhatsApp phone number.'):
            with self.subTest(message=message):
                verdict = self.adapter.parse_error(WhatsAppError(message, permanent=True))
                self.assertEqual(verdict['error_code'], 'WHATSAPP_NOT_CONFIGURED')
                self.assertFalse(verdict['retryable'])
                self.assertIsNone(verdict['retry_after_seconds'])

    def test_permanence_wins_over_an_http_status(self):
        """A pre-flight failure never reached the provider, so any status on it
        is noise rather than a verdict."""
        verdict = self.adapter.parse_error(
            WhatsAppError('no token', http_status=429, permanent=True))
        self.assertFalse(verdict['retryable'])

    def test_unknown_codes_retry(self):
        verdict = self.verdict(999999)
        self.assertEqual(verdict['error_code'], 'WHATSAPP_ERROR')
        self.assertTrue(verdict['retryable'])

    def test_connection_failure_retries(self):
        verdict = self.adapter.parse_error(WhatsAppError('no route', http_status=0))
        self.assertTrue(verdict['retryable'])

    def test_a_plain_exception_does_not_crash_classification(self):
        """_handle_failure calls this with whatever went wrong, not only ours."""
        verdict = self.adapter.parse_error(ValueError('unexpected'))
        self.assertEqual(verdict['error_code'], 'WHATSAPP_ERROR')
        self.assertTrue(verdict['retryable'])


class TestWhatsAppParseInbound(TransactionCase):
    def setUp(self):
        super().setUp()
        self.adapter = WhatsAppAdapter()

    def test_text_message(self):
        events = self.adapter.parse_inbound(fixtures.inbound_text())
        self.assertEqual(len(events), 1)
        event = events[0]
        self.assertEqual(event['event_type'], 'message')
        self.assertEqual(event['external_message_id'], fixtures.INBOUND_WAMID)
        self.assertEqual(event['sender_identifier'], fixtures.CUSTOMER_WA_ID)
        self.assertEqual(event['external_username'], 'Test Customer')
        self.assertEqual(event['text'], 'Do you ship to Izmir?')
        self.assertTrue(event['supported'])
        # This is what resolves the company. Inbound payloads carry no 'to'.
        self.assertEqual(event['phone_number_id'], fixtures.PHONE_NUMBER_ID)

    def test_unsupported_type_is_recorded_not_dropped(self):
        events = self.adapter.parse_inbound(fixtures.inbound_unsupported())
        self.assertEqual(len(events), 1)
        self.assertFalse(events[0]['supported'])
        self.assertEqual(events[0]['message_type'], 'sticker')
        self.assertIsNone(events[0]['text'])
        self.assertEqual(events[0]['external_message_id'], fixtures.INBOUND_WAMID)

    def test_status_notification(self):
        events = self.adapter.parse_inbound(fixtures.status('read'))
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]['event_type'], 'status')
        self.assertEqual(events[0]['status'], 'read')
        self.assertEqual(events[0]['external_message_id'], fixtures.OUTBOUND_WAMID)

    def test_batched_messages_all_survive(self):
        events = self.adapter.parse_inbound(fixtures.two_messages_one_notification())
        self.assertEqual(len(events), 2)
        self.assertEqual({event['text'] for event in events}, {'First', 'Second'})

    def test_empty_and_unknown_payloads_do_not_raise(self):
        self.assertEqual(self.adapter.parse_inbound({}), [])
        self.assertEqual(self.adapter.parse_inbound({'entry': [{'changes': [{}]}]}), [])


class TestWhatsAppIdentity(TransactionCase):
    def setUp(self):
        super().setUp()
        self.adapter = WhatsAppAdapter()

    def test_variations_of_one_number_normalize_alike(self):
        """wa_id comes back unplussed; humans type it every other way.

        Storing both shapes would give one customer two identities, which is
        the whole reason identities normalize before matching.
        """
        for raw in ('905111111111', '+905111111111', '+90 511 111 11 11',
                    '+90-511-111-11-11', '(90) 511 111 11 11'):
            with self.subTest(raw=raw):
                self.assertEqual(self.adapter.normalize_identity(raw), '+905111111111')

    def test_empty_input_yields_nothing(self):
        self.assertIsNone(self.adapter.normalize_identity(''))
        self.assertIsNone(self.adapter.normalize_identity(None))
        self.assertIsNone(self.adapter.normalize_identity('not a number'))

    def test_capabilities_report_what_is_actually_built(self):
        capabilities = self.adapter.capabilities()
        self.assertTrue(capabilities['supports_text'])
        self.assertTrue(capabilities['supports_templates'])
        # Media is phase 11. Claiming it here would have the future inbox offer
        # an attachment button that cannot work.
        self.assertFalse(capabilities['supports_media'])


class TestWhatsAppThroughTheQueue(TransactionCase):
    """The classification claims, proven through the foundry rather than at the seam.

    parse_error returning `retryable: False` is only interesting if
    action_process and _handle_failure actually act on it. These go through the
    real queue so the wiring is asserted, not assumed.
    """

    def setUp(self):
        super().setUp()
        from odoo.addons.midvex_o_notification_foundry.tests.common import ensure_channel

        channel = ensure_channel(self.env, 'whatsapp', 'WhatsApp')
        self.account = self.env['midvex.notification.account'].create({
            'name': 'Test WhatsApp', 'channel_id': channel.id,
            'wa_phone_number_id': fixtures.PHONE_NUMBER_ID,
            'api_key': 'TOKEN-PLACEHOLDER',
        })
        self.recipient = self.env['midvex.notification.recipient'].create({
            'kind': 'user', 'user_id': self.env.user.id, 'account_id': self.account.id,
            'state': 'linked',
        })

    def queue(self, key='wa-queue-1'):
        return self.env['midvex.notification.message'].create({
            'name': 'Test', 'recipient_id': self.recipient.id, 'account_id': self.account.id,
            'body': 'Hello', 'idempotency_key': key,
        })

    def test_a_recipient_with_no_number_is_quarantined_on_the_first_attempt(self):
        """Not retried three times over half an hour and then called failed.

        Quarantined means "a human must fix this", which is exactly what an
        unlinked recipient needs. The distinction is invisible in the adapter
        and very visible in the queue.
        """
        message = self.queue()
        self.assertFalse(self.recipient.external_id)
        message.action_process()
        self.assertEqual(message.state, 'quarantined')
        self.assertEqual(message.error_code, 'WHATSAPP_NOT_CONFIGURED')
        self.assertEqual(message.attempt_count, 1)
        self.assertFalse(message.next_retry_at)

    def test_a_rate_limit_hands_back_the_attempt(self):
        """ADR-012, in a second channel.

        Being rate-limited says nothing about the message. If the attempt were
        counted, a busy hour would destroy alerts that were never really tried.
        """
        from odoo.addons.midvex_o_notification_foundry.services.registry import get_adapter

        self.recipient.external_id = '+%s' % fixtures.CUSTOMER_WA_ID
        adapter = get_adapter('whatsapp')
        original = adapter.client.send_message
        adapter.client.send_message = lambda account, payload: (_ for _ in ()).throw(
            WhatsAppError('too fast', code=130429, http_status=429))
        try:
            message = self.queue('wa-queue-2')
            message.action_process()
        finally:
            # The registry holds one adapter for the process lifetime, so a
            # stub left in place would follow this test into every later one.
            adapter.client.send_message = original

        self.assertEqual(message.state, 'pending')
        self.assertEqual(message.error_code, 'WHATSAPP_RATE_LIMIT')
        self.assertEqual(message.attempt_count, 0)
        self.assertTrue(message.next_retry_at)

    def test_a_closed_messaging_window_is_quarantined(self):
        """131047 cannot be retried into success — only a template can."""
        from odoo.addons.midvex_o_notification_foundry.services.registry import get_adapter

        self.recipient.external_id = '+%s' % fixtures.CUSTOMER_WA_ID
        adapter = get_adapter('whatsapp')
        original = adapter.client.send_message
        adapter.client.send_message = lambda account, payload: (_ for _ in ()).throw(
            WhatsAppError('window closed', code=131047, http_status=400))
        try:
            message = self.queue('wa-queue-3')
            message.action_process()
        finally:
            adapter.client.send_message = original

        self.assertEqual(message.state, 'quarantined')
        self.assertEqual(message.error_code, 'WHATSAPP_POLICY_RESTRICTED')

    def test_a_successful_send_stores_the_wamid_and_reaches_sent(self):
        from odoo.addons.midvex_o_notification_foundry.services.registry import get_adapter

        self.recipient.external_id = '+%s' % fixtures.CUSTOMER_WA_ID
        adapter = get_adapter('whatsapp')
        original = adapter.client.send_message
        adapter.client.send_message = lambda account, payload: fixtures.send_success()
        try:
            message = self.queue('wa-queue-4')
            message.action_process()
        finally:
            adapter.client.send_message = original

        self.assertEqual(message.state, 'sent')
        # The stored compute is what the webhook searches on. Without it a
        # delivery status can never find the row it belongs to.
        self.assertEqual(message.wa_message_id, fixtures.OUTBOUND_WAMID)


class TestWhatsAppRegistration(TransactionCase):
    def test_the_adapter_is_registered_under_its_channel_code(self):
        from odoo.addons.midvex_o_notification_foundry.services.registry import (
            available_adapter_codes, get_adapter)
        self.assertIn('whatsapp', available_adapter_codes())
        self.assertIsInstance(get_adapter('whatsapp'), WhatsAppAdapter)

    def test_the_channel_record_ships_with_the_module(self):
        channel = self.env.ref('midvex_o_notification_whatsapp.channel_whatsapp')
        self.assertEqual(channel.code, 'whatsapp')
        self.assertTrue(channel.supports_inbound)

    def test_rate_limits_are_declared_for_the_foundry_to_read(self):
        """_throttle_release_at reads these off the adapter.

        Six seconds per recipient is WhatsApp's published pair limit; an
        adapter that declared none would never be throttled at all.
        """
        adapter = WhatsAppAdapter()
        self.assertEqual(adapter.rate_limit_chat_seconds, 6)
        self.assertEqual(adapter.rate_limit_global_per_second, 80)
