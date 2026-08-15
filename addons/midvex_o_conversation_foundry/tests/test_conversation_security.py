from odoo.exceptions import AccessError

from odoo.addons.midvex_o_conversation_foundry.services import conversation

from .common import ConversationCase


class ConversationSecurityCase(ConversationCase):
    """One agent who works for company A only, and data in both companies."""

    def setUp(self):
        super().setUp()
        group = self.env.ref('midvex_o_notification_foundry.group_notification_user')
        self.agent_a = self.env['res.users'].create({
            'name': 'Agent A', 'login': 'conv_sec_agent_a',
            'company_id': self.company_a.id, 'company_ids': [(6, 0, [self.company_a.id])],
            'group_ids': [(4, group.id)],
        })
        self.session_a = self.session(
            self.thread(self.company_a, self.identity(self.company_a, '+905111111111')),
            self.account_a, '+905111111111')
        self.session_b = self.session(
            self.thread(self.company_b, self.identity(self.company_b, '+905222222222')),
            self.account_b, '+905222222222')
        self.message_a = conversation.record_inbound(
            self.env, self.session_a, {'external_message_id': 'a.1', 'body': 'A'})
        self.message_b = conversation.record_inbound(
            self.env, self.session_b, {'external_message_id': 'b.1', 'body': 'B'})


class TestConversationIsolation(ConversationSecurityCase):
    """Company isolation asserted with with_user, never by reading the rule back.

    The acceptance criteria are explicit that a view domain is not isolation,
    and access rights say who may read the model rather than which rows of it.
    """

    def test_threads_are_scoped(self):
        visible = self.Thread.with_user(self.agent_a).search([])
        self.assertIn(self.session_a.thread_id, visible)
        self.assertNotIn(self.session_b.thread_id, visible)

    def test_another_companys_thread_cannot_be_read(self):
        with self.assertRaises(AccessError):
            self.session_b.thread_id.with_user(self.agent_a).read(['name'])

    def test_another_companys_thread_cannot_be_written(self):
        with self.assertRaises(AccessError):
            self.session_b.thread_id.with_user(self.agent_a).write({'priority': '2'})

    def test_messages_are_scoped(self):
        visible = self.Message.with_user(self.agent_a).search([])
        self.assertIn(self.message_a, visible)
        self.assertNotIn(self.message_b, visible)

    def test_another_companys_message_cannot_be_read(self):
        """The one that matters most: this is the customer's words."""
        with self.assertRaises(AccessError):
            self.message_b.with_user(self.agent_a).read(['body'])

    def test_sessions_are_scoped(self):
        visible = self.Session.with_user(self.agent_a).search([])
        self.assertIn(self.session_a, visible)
        self.assertNotIn(self.session_b, visible)

    def test_identities_are_scoped(self):
        """A customer list is a company's own. Leaking it leaks who they sell to."""
        visible = self.Identity.with_user(self.agent_a).search([])
        self.assertIn(self.session_a.thread_id.identity_id, visible)
        self.assertNotIn(self.session_b.thread_id.identity_id, visible)

    def test_assignment_history_is_scoped(self):
        agent_b = self.env['res.users'].create({
            'name': 'Agent B', 'login': 'conv_sec_agent_b',
            'company_id': self.company_b.id, 'company_ids': [(6, 0, [self.company_b.id])],
        })
        self.session_b.thread_id.action_assign(agent_b)
        Event = self.env['midvex.conversation.assignment.event']
        visible = Event.with_user(self.agent_a).search([])
        self.assertFalse(visible.filtered(
            lambda event: event.thread_id == self.session_b.thread_id))

    def test_a_user_in_both_companies_sees_both(self):
        """company_ids, not company_id: somebody allowed into two companies
        should see both, not only the one they currently have selected."""
        group = self.env.ref('midvex_o_notification_foundry.group_notification_user')
        both = self.env['res.users'].create({
            'name': 'Group Supervisor', 'login': 'conv_sec_both',
            'company_id': self.company_a.id,
            'company_ids': [(6, 0, [self.company_a.id, self.company_b.id])],
            'group_ids': [(4, group.id)],
        })
        visible = self.Thread.with_user(both).search([])
        self.assertIn(self.session_a.thread_id, visible)
        self.assertIn(self.session_b.thread_id, visible)


class TestConversationImmutability(ConversationSecurityCase):
    """History and audit trails are append-only, by access rights.

    Not a philosophical position: the runbook's answer to "duplicate messages"
    and "wrong company" both start by reading what actually happened, and a
    record somebody could quietly delete cannot answer that.
    """

    def test_nobody_can_delete_a_message(self):
        manager = self.env.ref('midvex_o_notification_foundry.group_notification_manager')
        self.agent_a.write({'group_ids': [(4, manager.id)]})
        with self.assertRaises(AccessError):
            self.message_a.with_user(self.agent_a).unlink()

    def test_nobody_can_delete_assignment_history(self):
        manager = self.env.ref('midvex_o_notification_foundry.group_notification_manager')
        self.agent_a.write({'group_ids': [(4, manager.id)]})
        self.session_a.thread_id.action_assign(self.agent_a)
        event = self.session_a.thread_id.assignment_event_ids
        with self.assertRaises(AccessError):
            event.with_user(self.agent_a).unlink()

    def test_assignment_history_cannot_be_rewritten(self):
        self.session_a.thread_id.action_assign(self.agent_a)
        event = self.session_a.thread_id.assignment_event_ids
        with self.assertRaises(AccessError):
            event.with_user(self.agent_a).write({'reason': 'something else'})
