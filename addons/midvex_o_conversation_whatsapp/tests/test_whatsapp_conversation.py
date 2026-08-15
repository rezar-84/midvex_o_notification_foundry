from datetime import timedelta

from odoo import fields
from odoo.exceptions import UserError
from odoo.tests.common import TransactionCase

from odoo.addons.midvex_o_conversation_foundry.services import conversation
from odoo.addons.midvex_o_notification_foundry.tests.common import ensure_channel
from odoo.addons.midvex_o_notification_whatsapp.tests import fixtures


class WhatsAppConversationCase(TransactionCase):
    def setUp(self):
        super().setUp()
        self.channel = ensure_channel(self.env, 'whatsapp', 'WhatsApp')
        self.company = self.env['res.company'].create({'name': 'WA Conversation Co'})
        self.account = self.env['midvex.notification.account'].create({
            'name': 'WA account', 'channel_id': self.channel.id,
            'company_id': self.company.id,
            'wa_phone_number_id': fixtures.PHONE_NUMBER_ID,
            'api_key': 'TOKEN-PLACEHOLDER',
        })
        self.Inbound = self.env['midvex.notification.inbound.event']
        self.Thread = self.env['midvex.conversation.thread']
        self.Message = self.env['midvex.conversation.message']

    def envelope(self, **values):
        """The stored envelope the webhook would have written."""
        return self.Inbound.create(dict({
            'channel_id': self.channel.id,
            'account_id': self.account.id,
            'event_type': 'message',
        }, **values))

    def inbound_event(self, body='Do you ship to Izmir?', wamid=None, **extra):
        """A parsed event, exactly as WhatsAppAdapter.parse_inbound returns one."""
        return dict({
            'event_type': 'message',
            'external_id': wamid or fixtures.INBOUND_WAMID,
            'external_message_id': wamid or fixtures.INBOUND_WAMID,
            'sender_identifier': fixtures.CUSTOMER_WA_ID,
            'external_username': 'Test Customer',
            'message_type': 'text',
            'text': body,
            'timestamp': '1749416383',
            'supported': True,
            'phone_number_id': fixtures.PHONE_NUMBER_ID,
            'waba_id': fixtures.WABA_ID,
        }, **extra)


class TestInboundThreading(WhatsAppConversationCase):
    def test_a_customer_message_becomes_a_conversation(self):
        """The whole point of the bridge: text stops being stored and dropped."""
        event = self.envelope()
        message = event.process_conversation_event(self.account, self.inbound_event())

        self.assertTrue(message)
        self.assertEqual(message.direction, 'inbound')
        self.assertEqual(message.body, 'Do you ship to Izmir?')
        thread = message.thread_id
        self.assertEqual(thread.company_id, self.company)
        self.assertEqual(thread.last_channel_code, 'whatsapp')
        self.assertTrue(thread.unanswered)

    def test_the_identity_is_normalized_to_e164(self):
        """wa_id comes back unplussed. Stored both ways, one person becomes two."""
        event = self.envelope()
        message = event.process_conversation_event(self.account, self.inbound_event())
        identity = message.thread_id.identity_id
        self.assertEqual(identity.normalized_identifier, '+%s' % fixtures.CUSTOMER_WA_ID)
        self.assertEqual(identity.identity_type, 'whatsapp')
        self.assertEqual(identity.company_id, self.company)

    def test_the_envelope_is_marked_off_against_what_it_produced(self):
        event = self.envelope()
        message = event.process_conversation_event(self.account, self.inbound_event())
        self.assertEqual(event.conversation_message_id, message)
        self.assertEqual(event.conversation_thread_id, message.thread_id)
        self.assertEqual(event.processing_state, 'processed')

    def test_two_messages_from_one_person_share_a_thread(self):
        first = self.envelope().process_conversation_event(
            self.account, self.inbound_event(body='One', wamid='wamid.1'))
        second = self.envelope().process_conversation_event(
            self.account, self.inbound_event(body='Two', wamid='wamid.2'))
        self.assertEqual(first.thread_id, second.thread_id)
        self.assertEqual(len(first.thread_id.message_ids), 2)

    def test_two_people_get_two_threads(self):
        first = self.envelope().process_conversation_event(
            self.account, self.inbound_event(wamid='wamid.1'))
        second = self.envelope().process_conversation_event(
            self.account, self.inbound_event(
                wamid='wamid.2', sender_identifier='905999999999'))
        self.assertNotEqual(first.thread_id, second.thread_id)

    def test_a_redelivered_message_does_not_duplicate(self):
        """The webhook dedupes the envelope, but a bridge that ran twice for
        any other reason must not produce a second message either."""
        event = self.envelope()
        first = event.process_conversation_event(self.account, self.inbound_event())
        second = event.process_conversation_event(self.account, self.inbound_event())
        self.assertEqual(first, second)
        self.assertEqual(len(first.thread_id.message_ids), 1)

    def test_the_company_comes_from_the_account_not_the_sender(self):
        """An inbound payload carries no `to`, and the sender is the one thing
        an attacker chooses. Resolution is from the account the webhook matched."""
        other_company = self.env['res.company'].create({'name': 'Other WA Co'})
        other_account = self.env['midvex.notification.account'].create({
            'name': 'Other WA', 'channel_id': self.channel.id,
            'company_id': other_company.id, 'wa_phone_number_id': '400000000000004',
        })
        event = self.Inbound.create({
            'channel_id': self.channel.id, 'account_id': other_account.id,
            'event_type': 'message',
        })
        message = event.process_conversation_event(other_account, self.inbound_event())
        self.assertEqual(message.thread_id.company_id, other_company)

    def test_an_unsupported_type_is_threaded_with_its_type_and_no_body(self):
        """So an agent sees "the customer sent an image", not an empty line."""
        event = self.envelope()
        message = event.process_conversation_event(
            self.account,
            self.inbound_event(body=None, message_type='image', supported=False))
        self.assertEqual(message.message_type, 'image')
        self.assertFalse(message.body)

    def test_a_message_with_no_sender_is_ignored_not_failed(self):
        """Nothing is wrong; there is simply nobody to attribute it to."""
        event = self.envelope()
        result = event.process_conversation_event(
            self.account, self.inbound_event(sender_identifier=None))
        self.assertFalse(result)
        self.assertEqual(event.processing_state, 'ignored')

    def test_the_providers_timestamp_is_used(self):
        event = self.envelope()
        message = event.process_conversation_event(self.account, self.inbound_event())
        # 1749416383 is 2025-06-08 in UTC; the exact value matters less than
        # that it is not "now".
        self.assertTrue(message.thread_id.last_message_at)
        self.assertLess(str(message.thread_id.last_message_at), '2026-01-01')

    def test_an_unparseable_timestamp_falls_back_rather_than_raising(self):
        event = self.envelope()
        message = event.process_conversation_event(
            self.account, self.inbound_event(timestamp='not-a-number'))
        self.assertTrue(message)


class TestStatusBridging(WhatsAppConversationCase):
    def outbound(self):
        """A reply that has been sent, so a status has something to land on."""
        inbound = self.envelope().process_conversation_event(
            self.account, self.inbound_event())
        session = inbound.session_id
        message = conversation.queue_outbound(self.env, session, 'We ship weekly.')
        message.write({'provider_message_id': fixtures.OUTBOUND_WAMID})
        message._apply_delivery_state('sent')
        return message

    def status_event(self, status='delivered', errors=None):
        return {
            'event_type': 'status',
            'external_id': fixtures.OUTBOUND_WAMID,
            'external_message_id': fixtures.OUTBOUND_WAMID,
            'status': status,
            'timestamp': '1750263773',
            'errors': errors or [],
        }

    def test_a_delivery_status_reaches_the_conversation_message(self):
        message = self.outbound()
        self.envelope(event_type='status').process_conversation_event(
            self.account, self.status_event('delivered'))
        self.assertEqual(message.state, 'delivered')

    def test_read_before_delivered_does_not_go_backwards(self):
        message = self.outbound()
        self.envelope(event_type='status').process_conversation_event(
            self.account, self.status_event('read'))
        self.envelope(event_type='status').process_conversation_event(
            self.account, self.status_event('delivered'))
        self.assertEqual(message.state, 'read')

    def test_a_failure_status_carries_the_providers_own_explanation(self):
        message = self.outbound()
        self.envelope(event_type='status').process_conversation_event(
            self.account, self.status_event('failed', errors=[{
                'code': 131026, 'title': 'Message undeliverable',
                'error_data': {'details': 'Receiver is incapable of receiving this message.'},
            }]))
        self.assertEqual(message.state, 'failed')
        self.assertEqual(message.error_code, '131026')
        self.assertIn('incapable', message.error_message_safe)

    def test_a_status_for_an_unknown_message_is_ignored(self):
        result = self.envelope(event_type='status').process_conversation_event(
            self.account, dict(self.status_event(), external_message_id='never-sent'))
        self.assertFalse(result)

    def test_an_unrecognised_status_is_recorded_as_ignored(self):
        """Meta adds statuses. An unknown one must not look like a failure."""
        self.outbound()
        event = self.envelope(event_type='status')
        event.process_conversation_event(
            self.account, self.status_event('something_new'))
        self.assertEqual(event.processing_state, 'ignored')


class TestAdapterToConversation(WhatsAppConversationCase):
    """Real adapter output, fed to the bridge.

    Every test above hand-builds the parsed event, which proves the bridge and
    assumes the seam. These run Meta's own published payload shapes through
    `WhatsAppAdapter.parse_inbound` and feed whatever comes out — so if the
    adapter's keys ever drift from what the bridge reads, this fails rather
    than production going quiet.
    """

    def parse(self, payload):
        from odoo.addons.midvex_o_notification_whatsapp.services.whatsapp_adapter import (
            WhatsAppAdapter)
        return WhatsAppAdapter().parse_inbound(payload)

    def test_a_real_inbound_payload_becomes_a_conversation(self):
        events = self.parse(fixtures.inbound_text())
        self.assertEqual(len(events), 1)
        message = self.envelope().process_conversation_event(self.account, events[0])
        self.assertTrue(message)
        self.assertEqual(message.body, 'Do you ship to Izmir?')
        self.assertEqual(
            message.thread_id.identity_id.normalized_identifier,
            '+%s' % fixtures.CUSTOMER_WA_ID)

    def test_a_batched_payload_threads_every_message(self):
        """Meta batches. An adapter or bridge that took only the first would
        lose the second silently — the customer's follow-up, usually."""
        events = self.parse(fixtures.two_messages_one_notification())
        self.assertEqual(len(events), 2)
        messages = [self.envelope().process_conversation_event(self.account, event)
                    for event in events]
        self.assertEqual({m.body for m in messages}, {'First', 'Second'})
        self.assertEqual(messages[0].thread_id, messages[1].thread_id)

    def test_a_real_unsupported_payload_does_not_crash_the_bridge(self):
        """A sticker used to raise inside the webhook.

        `sticker` is not a value the message_type Selection can hold, so the
        ORM refused it — which crashed the handler and, because Meta batches,
        would have taken every message alongside it. It is now `other`, with
        the provider's own word kept so an agent can see what actually arrived.
        """
        events = self.parse(fixtures.inbound_unsupported())
        message = self.envelope().process_conversation_event(self.account, events[0])
        self.assertEqual(message.message_type, 'other')
        self.assertEqual(message.provider_message_type, 'sticker')

    def test_an_invented_provider_type_survives(self):
        """Providers add types. None of them should be able to stop the webhook."""
        events = self.parse(fixtures.inbound_unsupported(message_type='reaction'))
        message = self.envelope().process_conversation_event(self.account, events[0])
        self.assertEqual(message.message_type, 'other')
        self.assertEqual(message.provider_message_type, 'reaction')

    def test_a_real_status_payload_reaches_the_conversation(self):
        inbound = self.envelope().process_conversation_event(
            self.account, self.inbound_event())
        reply = conversation.queue_outbound(
            self.env, inbound.session_id, 'We ship weekly.')
        reply.write({'provider_message_id': fixtures.OUTBOUND_WAMID})
        reply._apply_delivery_state('sent')

        events = self.parse(fixtures.status('read'))
        self.envelope(event_type='status').process_conversation_event(
            self.account, events[0])
        self.assertEqual(reply.state, 'read')

    def test_a_real_failed_status_marks_the_message_failed(self):
        inbound = self.envelope().process_conversation_event(
            self.account, self.inbound_event())
        reply = conversation.queue_outbound(
            self.env, inbound.session_id, 'We ship weekly.')
        reply.write({'provider_message_id': fixtures.OUTBOUND_WAMID})
        reply._apply_delivery_state('sent')

        events = self.parse(fixtures.status_failed())
        self.envelope(event_type='status').process_conversation_event(
            self.account, events[0])
        self.assertEqual(reply.state, 'failed')
        self.assertTrue(reply.error_message_safe)


class TestCustomerServiceWindow(WhatsAppConversationCase):
    def session_with_inbound(self, age=None):
        message = self.envelope().process_conversation_event(
            self.account, self.inbound_event())
        if age:
            message.create_date = fields.Datetime.now() - age
            message.session_id.invalidate_recordset()
        return message.session_id

    def test_a_recent_message_leaves_the_window_open(self):
        session = self.session_with_inbound()
        self.assertTrue(session.whatsapp_window_open)
        reply = conversation.queue_outbound(self.env, session, 'Yes, weekly.')
        self.assertTrue(reply)

    def test_a_free_form_reply_is_refused_once_the_window_closes(self):
        """Refused before the agent types, not after the provider says 131047."""
        session = self.session_with_inbound(age=timedelta(hours=25))
        self.assertFalse(session.whatsapp_window_open)
        with self.assertRaises(UserError) as caught:
            conversation.queue_outbound(self.env, session, 'Too late.')
        self.assertIn('24-hour', str(caught.exception))

    def test_a_template_is_still_allowed_outside_the_window(self):
        """A template is the thing that IS allowed there, so the window never
        refuses one."""
        session = self.session_with_inbound(age=timedelta(hours=25))
        reply = conversation.queue_outbound(
            self.env, session, 'Your quotation is ready.', message_type='template')
        self.assertTrue(reply)

    def test_the_window_closing_time_is_reported(self):
        session = self.session_with_inbound()
        self.assertTrue(session.whatsapp_window_closes_at)

    def test_a_session_the_customer_never_wrote_on_has_no_window(self):
        thread = conversation.ensure_thread(
            self.env, self.company,
            conversation.ensure_identity(
                self.env, self.company, 'whatsapp', '+905333333333'))
        session = conversation.open_session(
            self.env, thread, self.account, '+905333333333')
        self.assertFalse(session.whatsapp_window_open)
        with self.assertRaises(UserError):
            conversation.queue_outbound(self.env, session, 'Cold outreach.')

    def test_replying_does_not_extend_the_window_the_customer_opened(self):
        """Read from inbound messages, not from last_activity_at, which moves
        on outbound too — that would be exactly backwards."""
        session = self.session_with_inbound()
        closes_at = session.whatsapp_window_closes_at
        conversation.queue_outbound(self.env, session, 'A reply.')
        session.invalidate_recordset()
        self.assertEqual(session.whatsapp_window_closes_at, closes_at)

    def test_other_channels_are_unaffected(self):
        """Telegram has no window at all. Treating WhatsApp's constraints as
        universal would silently break every other channel's replies."""
        telegram = ensure_channel(self.env, 'telegram', 'Telegram')
        account = self.env['midvex.notification.account'].create({
            'name': 'TG', 'channel_id': telegram.id, 'company_id': self.company.id,
        })
        thread = conversation.ensure_thread(
            self.env, self.company,
            conversation.ensure_identity(
                self.env, self.company, 'telegram', 'chat-1'))
        session = conversation.open_session(self.env, thread, account, 'chat-1')
        self.assertTrue(session.whatsapp_window_open)
        self.assertTrue(conversation.queue_outbound(self.env, session, 'Anytime.'))
