from odoo.exceptions import ValidationError

from .common import ConversationCase


class TestConversationIdentity(ConversationCase):
    def test_the_same_address_resolves_to_one_identity(self):
        first = self.identity()
        second = self.identity()
        self.assertEqual(first, second)

    def test_the_same_address_in_two_companies_is_two_relationships(self):
        """One number contacting two companies in a group is two customers.

        Sharing an identity would mean one company's agent seeing the other's
        conversation history with that person, which is the leak the record
        rules exist to prevent — and it would defeat them, because the row
        would legitimately belong to both.
        """
        a = self.identity(self.company_a)
        b = self.identity(self.company_b)
        self.assertNotEqual(a, b)
        self.assertEqual(a.company_id, self.company_a)
        self.assertEqual(b.company_id, self.company_b)

    def test_an_identity_without_an_identifier_is_refused(self):
        with self.assertRaises(ValidationError):
            self.Identity.create({
                'identity_type': 'whatsapp', 'normalized_identifier': '   ',
                'company_id': self.company_a.id,
            })

    def test_the_unique_constraint_holds(self):
        from psycopg2 import IntegrityError
        self.identity()
        with self.assertRaises(IntegrityError), self.env.cr.savepoint():
            self.Identity.create({
                'identity_type': 'whatsapp', 'normalized_identifier': '+905111111111',
                'company_id': self.company_a.id,
            })

    def test_an_archived_identity_is_revived_rather_than_duplicated(self):
        """The same person coming back, not a new one.

        Creating a second would fail the unique constraint anyway; reviving is
        what keeps their history attached to them.
        """
        identity = self.identity()
        identity.active = False
        revived = self.identity()
        self.assertEqual(revived, identity)
        self.assertTrue(revived.active)

    def test_last_seen_moves_when_the_person_returns(self):
        identity = self.identity()
        identity.write({'last_seen_at': '2020-01-01 00:00:00'})
        self.identity()
        self.assertGreater(str(identity.last_seen_at), '2020-01-01')

    def test_linking_a_partner_marks_the_identity_verified(self):
        identity = self.identity()
        partner = self.env['res.partner'].create({'name': 'Known Customer'})
        identity.action_link_partner(partner)
        self.assertEqual(identity.partner_id, partner)
        self.assertTrue(identity.verified)

    def test_the_partner_reaches_every_thread_that_identity_has(self):
        """partner_id on the thread is related through the identity.

        Stored per thread it would have to be backfilled on every one of them
        when somebody is finally identified, and whichever was missed would
        stay anonymous.
        """
        identity = self.identity()
        thread = self.thread(identity=identity)
        partner = self.env['res.partner'].create({'name': 'Known Customer'})
        identity.action_link_partner(partner)
        self.assertEqual(thread.partner_id, partner)


class TestConversationThread(ConversationCase):
    def test_a_live_thread_is_reused(self):
        first = self.thread()
        second = self.thread()
        self.assertEqual(first, second)

    def test_a_resolved_thread_is_not_reused_for_a_new_enquiry(self):
        """Somebody coming back a month later about something else.

        Appending to the closed conversation would file a new enquiry under an
        old subject, where nobody is looking for it.
        """
        first = self.thread()
        first.action_resolve()
        second = self.thread()
        self.assertNotEqual(first, second)

    def test_a_thread_cannot_take_an_identity_from_another_company(self):
        foreign = self.identity(self.company_b)
        with self.assertRaises(ValidationError):
            self.Thread.create({
                'name': 'Cross company', 'company_id': self.company_a.id,
                'identity_id': foreign.id,
            })

    def test_assignment_is_audited(self):
        thread = self.thread()
        agent = self.env['res.users'].create({
            'name': 'Agent One', 'login': 'conv_agent_one',
            'company_id': self.company_a.id, 'company_ids': [(6, 0, [self.company_a.id])],
        })
        thread.action_assign(agent, reason='initial triage')
        event = thread.assignment_event_ids
        self.assertEqual(len(event), 1)
        self.assertEqual(event.to_user_id, agent)
        self.assertEqual(event.reason, 'initial triage')

    def test_taking_an_untouched_conversation_opens_it(self):
        """Otherwise it keeps appearing in the queue somebody just claimed it from."""
        thread = self.thread()
        agent = self.env['res.users'].create({
            'name': 'Agent Two', 'login': 'conv_agent_two',
            'company_id': self.company_a.id, 'company_ids': [(6, 0, [self.company_a.id])],
        })
        self.assertEqual(thread.status, 'new')
        thread.action_assign(agent)
        self.assertEqual(thread.status, 'open')

    def test_reassigning_to_the_same_person_records_nothing(self):
        thread = self.thread()
        agent = self.env['res.users'].create({
            'name': 'Agent Three', 'login': 'conv_agent_three',
            'company_id': self.company_a.id, 'company_ids': [(6, 0, [self.company_a.id])],
        })
        thread.action_assign(agent)
        thread.action_assign(agent)
        self.assertEqual(len(thread.assignment_event_ids), 1)

    def test_a_thread_cannot_be_assigned_across_companies(self):
        from odoo.exceptions import UserError
        thread = self.thread(self.company_a)
        outsider = self.env['res.users'].create({
            'name': 'Other Co Agent', 'login': 'conv_agent_other',
            'company_id': self.company_b.id, 'company_ids': [(6, 0, [self.company_b.id])],
        })
        with self.assertRaises(UserError):
            thread.action_assign(outsider)

    def test_reopening_clears_the_resolution_time(self):
        """It is no longer true, and leaving it would overstate how fast
        things get closed."""
        thread = self.thread()
        thread.action_resolve()
        self.assertTrue(thread.resolved_at)
        thread.action_reopen()
        self.assertFalse(thread.resolved_at)
        self.assertEqual(thread.status, 'waiting_agent')


class TestConversationSession(ConversationCase):
    def test_the_company_invariant_is_enforced_server_side(self):
        """thread.company == session.company == account.company.

        The rule the whole security model rests on. Violated, one company's
        branded number writes to a customer on another company's behalf — not a
        permissions bug the customer can see, but the wrong business talking to
        them.
        """
        thread = self.thread(self.company_a)
        with self.assertRaises(ValidationError):
            self.Session.create({
                'thread_id': thread.id, 'channel_code': self.adapter.channel_code,
                'account_id': self.account_b.id, 'external_recipient_id': '+905111111111',
            })

    def test_a_session_cannot_use_another_channels_account(self):
        from odoo.addons.midvex_o_notification_foundry.tests.common import ensure_channel
        telegram = ensure_channel(self.env, 'telegram', 'Telegram')
        telegram_account = self.env['midvex.notification.account'].create({
            'name': 'Telegram A', 'channel_id': telegram.id, 'company_id': self.company_a.id,
        })
        thread = self.thread(self.company_a)
        with self.assertRaises(ValidationError):
            self.Session.create({
                'thread_id': thread.id, 'channel_code': self.adapter.channel_code,
                'account_id': telegram_account.id, 'external_recipient_id': 'x',
            })

    def test_a_session_needs_somewhere_to_reply(self):
        """Refused at the database, because the field is required.

        Asserted on the model as well as on the service because a session with
        nowhere to reply is a thread that can be read and never answered — and
        the failure would surface at send time, far from the cause.
        """
        from psycopg2 import IntegrityError
        thread = self.thread()
        with self.assertRaises(IntegrityError), self.env.cr.savepoint():
            self.Session.create({
                'thread_id': thread.id, 'channel_code': self.adapter.channel_code,
                'account_id': self.account_a.id,
            })

    def test_the_service_refuses_a_session_with_no_address_readably(self):
        """The same refusal one layer up, where a caller can act on it."""
        from odoo.addons.midvex_o_conversation_foundry.services import conversation
        thread = self.thread()
        with self.assertRaises(ValidationError):
            conversation.open_session(self.env, thread, self.account_a, None)

    def test_the_open_session_is_reused(self):
        """A session is the leg, not the exchange.

        One per message would make the history look like a customer who kept
        switching channel.
        """
        thread = self.thread()
        first = self.session(thread)
        second = self.session(thread)
        self.assertEqual(first, second)

    def test_one_thread_can_carry_two_channels(self):
        """The entire reason thread and session are two models."""
        thread = self.thread(self.company_a)
        first = self.session(thread, self.account_a, '+905111111111')
        second_account = self.env['midvex.notification.account'].create({
            'name': 'Account A2', 'channel_id': self.channel.id,
            'company_id': self.company_a.id,
        })
        second = self.session(thread, second_account, 'web-token-abc')
        self.assertNotEqual(first, second)
        self.assertEqual(thread.session_ids, first + second)


class TestConversationMessage(ConversationCase):
    def test_a_customer_facing_message_needs_a_session(self):
        thread = self.thread()
        with self.assertRaises(ValidationError):
            self.Message.create({
                'thread_id': thread.id, 'direction': 'outbound', 'body': 'Hello',
            })

    def test_an_internal_note_needs_none(self):
        thread = self.thread()
        note = self.Message.create({
            'thread_id': thread.id, 'direction': 'internal', 'body': 'For colleagues',
        })
        self.assertFalse(note.session_id)

    def test_a_message_cannot_be_filed_under_a_foreign_session(self):
        first = self.thread(self.company_a, self.identity(self.company_a, '+905111111111'))
        other = self.thread(self.company_a, self.identity(self.company_a, '+905222222222'))
        other_session = self.session(other, self.account_a, '+905222222222')
        with self.assertRaises(ValidationError):
            self.Message.create({
                'thread_id': first.id, 'session_id': other_session.id,
                'direction': 'outbound', 'body': 'Wrong thread',
            })

    def test_the_delivery_ladder_only_climbs(self):
        session = self.session()
        message = self.Message.create({
            'thread_id': session.thread_id.id, 'session_id': session.id,
            'direction': 'outbound', 'body': 'Hello', 'state': 'queued',
        })
        self.assertTrue(message._apply_delivery_state('sent'))
        self.assertTrue(message._apply_delivery_state('read'))
        # `delivered` after `read` is the ordinary case, not an edge case.
        self.assertFalse(message._apply_delivery_state('delivered'))
        self.assertEqual(message.state, 'read')

    def test_reaching_a_state_stamps_it_once(self):
        session = self.session()
        message = self.Message.create({
            'thread_id': session.thread_id.id, 'session_id': session.id,
            'direction': 'outbound', 'body': 'Hello',
        })
        message._apply_delivery_state('delivered')
        first_stamp = message.delivered_at
        message._apply_delivery_state('read')
        self.assertEqual(message.delivered_at, first_stamp)

    def test_failure_is_terminal_and_outside_the_ladder(self):
        """A message that failed did not get further than one merely sent."""
        session = self.session()
        message = self.Message.create({
            'thread_id': session.thread_id.id, 'session_id': session.id,
            'direction': 'outbound', 'body': 'Hello',
        })
        message._apply_failure(error_code='NOPE', safe_message='Recipient unreachable.')
        self.assertEqual(message.state, 'failed')
        self.assertEqual(message.error_code, 'NOPE')
        self.assertFalse(message._apply_delivery_state('failed'))

    def test_one_provider_message_is_recorded_once_per_session(self):
        from psycopg2 import IntegrityError
        session = self.session()
        values = {
            'thread_id': session.thread_id.id, 'session_id': session.id,
            'direction': 'inbound', 'body': 'Hello', 'provider_message_id': 'wamid.X',
        }
        self.Message.create(values)
        with self.assertRaises(IntegrityError), self.env.cr.savepoint():
            self.Message.create(values)
