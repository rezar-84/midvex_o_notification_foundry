from odoo.exceptions import UserError

from odoo.addons.midvex_o_conversation_foundry.services import conversation

from .common import ConversationCase


class TestRecordInbound(ConversationCase):
    def inbound(self, body='Do you ship to Izmir?', message_id='wamid.A', **extra):
        return dict({
            'external_message_id': message_id,
            'message_type': 'text',
            'body': body,
        }, **extra)

    def test_an_inbound_message_lands_on_the_thread(self):
        session = self.session()
        message = conversation.record_inbound(self.env, session, self.inbound())
        self.assertEqual(message.direction, 'inbound')
        self.assertEqual(message.body, 'Do you ship to Izmir?')
        self.assertEqual(message.thread_id, session.thread_id)
        # It did not travel through our queue, so there is no ladder to climb.
        self.assertEqual(message.state, 'delivered')
        self.assertEqual(message.origin, 'provider')

    def test_a_redelivered_webhook_does_not_duplicate_the_message(self):
        """FR-007. Providers retry, and a retry that is not idempotent here
        shows the customer's question twice and, later, makes two leads."""
        session = self.session()
        first = conversation.record_inbound(self.env, session, self.inbound())
        second = conversation.record_inbound(self.env, session, self.inbound())
        self.assertEqual(first, second)
        self.assertEqual(len(session.thread_id.message_ids), 1)

    def test_the_thread_moves_to_waiting_on_us(self):
        session = self.session()
        thread = session.thread_id
        agent = self.env['res.users'].create({
            'name': 'Agent Inbound', 'login': 'conv_agent_inbound',
            'company_id': self.company_a.id, 'company_ids': [(6, 0, [self.company_a.id])],
        })
        thread.action_assign(agent)
        conversation.record_inbound(self.env, session, self.inbound())
        self.assertEqual(thread.status, 'waiting_agent')
        self.assertTrue(thread.unanswered)

    def test_a_reply_mid_conversation_puts_the_ball_back_with_us(self):
        """An ongoing exchange, which is the ordinary case.

        The first version of this transition read only `new` and
        `waiting_customer`, so a customer replying to a thread already `open`
        left the status saying nothing was owed — while `unanswered` said
        otherwise. Two fields disagreeing about the same fact is how an inbox
        filter starts hiding work.
        """
        session = self.session()
        thread = session.thread_id
        agent = self.env['res.users'].create({
            'name': 'Agent Mid', 'login': 'conv_agent_mid',
            'company_id': self.company_a.id, 'company_ids': [(6, 0, [self.company_a.id])],
        })
        thread.action_assign(agent)
        self.assertEqual(thread.status, 'open')
        conversation.record_inbound(self.env, session, self.inbound())
        self.assertEqual(thread.status, 'waiting_agent')

    def test_an_unclaimed_thread_stays_in_the_unassigned_queue(self):
        """Moving it to waiting_agent would imply an agent who does not exist."""
        session = self.session()
        thread = session.thread_id
        self.assertFalse(thread.assigned_user_id)
        conversation.record_inbound(self.env, session, self.inbound())
        self.assertEqual(thread.status, 'new')
        self.assertTrue(thread.unanswered)

    def test_a_customer_replying_reopens_a_resolved_thread(self):
        """Appending silently would put their message where nobody is looking."""
        session = self.session()
        thread = session.thread_id
        thread.action_resolve()
        conversation.record_inbound(self.env, session, self.inbound())
        self.assertEqual(thread.status, 'waiting_agent')
        self.assertFalse(thread.resolved_at)

    def test_the_first_channel_is_remembered(self):
        session = self.session()
        conversation.record_inbound(self.env, session, self.inbound())
        self.assertEqual(session.thread_id.first_channel_code, self.adapter.channel_code)
        self.assertEqual(session.thread_id.last_channel_code, self.adapter.channel_code)

    def test_the_detected_language_is_kept_but_never_overwrites_the_body(self):
        session = self.session()
        message = conversation.record_inbound(
            self.env, session, self.inbound(language_hint='tr_TR'))
        self.assertEqual(session.thread_id.language_code, 'tr_TR')
        self.assertEqual(message.original_language, 'tr_TR')
        self.assertEqual(message.body, 'Do you ship to Izmir?')

    def test_an_envelope_is_marked_off_against_what_it_produced(self):
        """ADR-019. Otherwise inbound events pile up looking unprocessed, and
        the runbook's daily check cries wolf."""
        session = self.session()
        event = self.env['midvex.notification.inbound.event'].create({
            'channel_id': self.channel.id, 'account_id': self.account_a.id,
            'event_type': 'message',
        })
        message = conversation.record_inbound(
            self.env, session, self.inbound(), inbound_event=event)
        self.assertEqual(event.conversation_message_id, message)
        self.assertEqual(event.conversation_thread_id, session.thread_id)
        self.assertEqual(event.processing_state, 'processed')
        self.assertTrue(event.processed)

    def test_an_unsupported_type_is_still_recorded(self):
        session = self.session()
        message = conversation.record_inbound(
            self.env, session, self.inbound(body=None, message_type='image'))
        self.assertEqual(message.message_type, 'image')
        self.assertFalse(message.body)


class TestQueueOutbound(ConversationCase):
    def test_a_reply_raises_a_delivery_job_in_the_one_queue(self):
        """ADR-020: no second queue. The durable message points at a row in the
        notification foundry's, and that row is what actually sends."""
        session = self.session()
        message = conversation.queue_outbound(self.env, session, 'We ship weekly.')
        self.assertTrue(message.delivery_id)
        self.assertEqual(message.delivery_id.account_id, self.account_a)
        self.assertEqual(message.delivery_id.sudo().destination_key, '+905111111111')
        self.assertEqual(message.state, 'submitted')

    def test_the_delivery_job_reaches_the_adapter_with_the_right_address(self):
        session = self.session()
        message = conversation.queue_outbound(self.env, session, 'We ship weekly.')
        message.delivery_id.action_process()
        self.assertEqual(len(self.adapter.send_calls), 1)
        self.assertEqual(self.adapter.send_calls[0]['recipient_external_id'],
                         '+905111111111')

    def test_a_sent_job_reports_back_to_the_conversation(self):
        """An agent watching the thread must not see their reply stuck at
        submitted until something unrelated happens to touch it."""
        session = self.session()
        message = conversation.queue_outbound(self.env, session, 'We ship weekly.')
        message.delivery_id.action_process()
        self.assertEqual(message.state, 'sent')
        self.assertEqual(message.provider_message_id, 'fake-1')
        self.assertTrue(message.sent_at)

    def test_a_failed_job_reports_back_as_failed(self):
        from odoo.exceptions import ValidationError
        session = self.session()
        message = conversation.queue_outbound(self.env, session, 'We ship weekly.')
        # ValidationError is what the queue quarantines on — a failure no retry
        # can fix.
        self.adapter.failure = ValidationError('Recipient is not reachable.')
        message.delivery_id.action_process()
        self.assertEqual(message.delivery_id.state, 'quarantined')
        self.assertEqual(message.state, 'failed')
        self.assertTrue(message.error_message_safe)

    def test_a_job_awaiting_retry_is_not_reported_as_failed(self):
        """It has not failed. Telling an agent it did would have them apologise
        for a message that is about to arrive."""
        session = self.session()
        message = conversation.queue_outbound(self.env, session, 'We ship weekly.')
        self.adapter.failure = UserError('Service Unavailable')
        message.delivery_id.action_process()
        self.assertEqual(message.delivery_id.state, 'pending')
        self.assertNotEqual(message.state, 'failed')

    def test_the_thread_moves_to_waiting_on_the_customer(self):
        session = self.session()
        thread = session.thread_id
        conversation.record_inbound(
            self.env, session, {'external_message_id': 'wamid.A', 'body': 'Hi'})
        self.assertTrue(thread.unanswered)
        conversation.queue_outbound(self.env, session, 'Hello back.')
        self.assertEqual(thread.status, 'waiting_customer')
        self.assertFalse(thread.unanswered)

    def test_the_first_response_time_is_stamped_once(self):
        """The number a supervisor actually cares about, and impossible to
        reconstruct after the fact."""
        session = self.session()
        thread = session.thread_id
        conversation.queue_outbound(self.env, session, 'First.')
        first = thread.first_response_at
        self.assertTrue(first)
        conversation.queue_outbound(self.env, session, 'Second.')
        self.assertEqual(thread.first_response_at, first)

    def test_a_closed_session_refuses_to_send(self):
        session = self.session()
        session.action_close()
        with self.assertRaises(UserError):
            conversation.queue_outbound(self.env, session, 'Too late.')

    def test_an_empty_reply_is_refused(self):
        session = self.session()
        with self.assertRaises(UserError):
            conversation.queue_outbound(self.env, session, '   ')

    def test_an_internal_note_never_reaches_the_customer(self):
        """No session, therefore no delivery job, therefore nothing that could
        accidentally be sent."""
        session = self.session()
        note = conversation.add_internal_note(
            self.env, session.thread_id, 'Customer sounds price-sensitive.')
        self.assertFalse(note.delivery_id)
        self.assertFalse(note.session_id)
        self.assertEqual(note.direction, 'internal')
        session.thread_id.message_ids.mapped('delivery_id').action_process()
        self.assertEqual(self.adapter.send_calls, [])

    def test_an_internal_note_does_not_count_as_answering(self):
        """A colleague reading the thread is not the customer hearing back."""
        session = self.session()
        thread = session.thread_id
        conversation.record_inbound(
            self.env, session, {'external_message_id': 'wamid.A', 'body': 'Hi'})
        conversation.add_internal_note(self.env, thread, 'Looks like a real lead.')
        self.assertTrue(thread.unanswered)


class TestApplyStatus(ConversationCase):
    def outbound(self):
        session = self.session()
        message = conversation.queue_outbound(self.env, session, 'We ship weekly.')
        message.delivery_id.action_process()
        return message

    def test_a_status_climbs_the_ladder(self):
        message = self.outbound()
        conversation.apply_status(self.env, self.account_a, 'fake-1', 'delivered')
        self.assertEqual(message.state, 'delivered')
        conversation.apply_status(self.env, self.account_a, 'fake-1', 'read')
        self.assertEqual(message.state, 'read')

    def test_out_of_order_statuses_do_not_undo_progress(self):
        message = self.outbound()
        conversation.apply_status(self.env, self.account_a, 'fake-1', 'read')
        conversation.apply_status(self.env, self.account_a, 'fake-1', 'delivered')
        self.assertEqual(message.state, 'read')

    def test_a_failure_status_is_recorded(self):
        message = self.outbound()
        conversation.apply_status(
            self.env, self.account_a, 'fake-1', 'failed',
            error_code='UNREACHABLE', safe_message='Not a WhatsApp user.')
        self.assertEqual(message.state, 'failed')
        self.assertEqual(message.error_code, 'UNREACHABLE')

    def test_a_status_for_an_unknown_message_is_ignored(self):
        """Normal: a shared number, or a row since pruned."""
        self.assertFalse(
            conversation.apply_status(self.env, self.account_a, 'never-sent', 'read'))

    def test_a_status_cannot_cross_accounts(self):
        """One company's status event must never touch another's message."""
        message = self.outbound()
        result = conversation.apply_status(self.env, self.account_b, 'fake-1', 'read')
        self.assertFalse(result)
        self.assertEqual(message.state, 'sent')


class TestThreadContinuity(ConversationCase):
    def test_one_thread_survives_the_customer_changing_channel(self):
        """The whole point of the thread/session split, end to end."""
        identity = self.identity(self.company_a)
        thread = self.thread(self.company_a, identity)
        whatsapp = self.session(thread, self.account_a, '+905111111111')
        conversation.record_inbound(
            self.env, whatsapp, {'external_message_id': 'wamid.A', 'body': 'On WhatsApp'})

        web_account = self.env['midvex.notification.account'].create({
            'name': 'Web widget', 'channel_id': self.channel.id,
            'company_id': self.company_a.id,
        })
        web = self.session(thread, web_account, 'web-token-1')
        conversation.record_inbound(
            self.env, web, {'external_message_id': 'web.1', 'body': 'Now on the site'})

        self.assertEqual(len(thread.session_ids), 2)
        self.assertEqual(len(thread.message_ids), 2)
        self.assertEqual(thread.last_channel_code, self.adapter.channel_code)

    def test_a_full_exchange_reads_in_order(self):
        session = self.session()
        thread = session.thread_id
        conversation.record_inbound(
            self.env, session, {'external_message_id': 'in.1', 'body': 'Question'})
        reply = conversation.queue_outbound(self.env, session, 'Answer')
        reply.delivery_id.action_process()
        conversation.record_inbound(
            self.env, session, {'external_message_id': 'in.2', 'body': 'Thanks'})

        bodies = thread.message_ids.sorted('id').mapped('body')
        self.assertEqual(bodies, ['Question', 'Answer', 'Thanks'])
        self.assertTrue(thread.unanswered)
