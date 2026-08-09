from odoo.exceptions import UserError
from odoo.tests.common import TransactionCase

from ..services import registry
from .common import ensure_channel
from .test_notification_dispatch import MockAdapter


class TestNotificationCompose(TransactionCase):
    """Sending by hand. The Message Queue offered a Create button for this and
    could never save the result, so composing lives in a wizard instead."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.adapter = MockAdapter()
        registry._ADAPTERS[cls.adapter.channel_code] = cls.adapter
        cls.channel = ensure_channel(cls.env, cls.adapter.channel_code, 'Mock Channel')
        cls.account = cls.env['midvex.notification.account'].create({
            'name': 'Compose account', 'channel_id': cls.channel.id, 'state': 'connected',
        })
        cls.room = cls.env['midvex.notification.recipient'].create({
            'kind': 'group', 'name': 'Compose room', 'account_id': cls.account.id,
            'state': 'linked', 'external_id': '-100555',
        })

    @classmethod
    def tearDownClass(cls):
        registry.unregister_adapter(cls.adapter.channel_code)
        super().tearDownClass()

    def test_sending_creates_and_delivers_a_message(self):
        sends_before = len(self.adapter.send_calls)
        wizard = self.env['midvex.notification.compose'].create({
            'account_id': self.account.id,
            'recipient_ids': [(6, 0, self.room.ids)],
            'body': 'Ad-hoc hello',
        })
        wizard.action_send()
        message = self.env['midvex.notification.message'].search(
            [('recipient_id', '=', self.room.id), ('body', '=', 'Ad-hoc hello')])
        self.assertEqual(len(message), 1)
        self.assertEqual(message.state, 'sent')
        self.assertFalse(message.rule_id, 'a manual send must not be attributed to a rule')
        self.assertEqual(len(self.adapter.send_calls), sends_before + 1)

    def test_it_ignores_quiet_hours(self):
        """A person pressing Send has decided it is worth the interruption -
        the same reasoning as the Retry button."""
        self.room.write({'quiet_enabled': True, 'quiet_start': 0.0, 'quiet_end': 23.5,
                          'tz': 'UTC'})
        wizard = self.env['midvex.notification.compose'].create({
            'account_id': self.account.id,
            'recipient_ids': [(6, 0, self.room.ids)],
            'body': 'Urgent',
        })
        wizard.action_send()
        message = self.env['midvex.notification.message'].search([('body', '=', 'Urgent')])
        self.assertEqual(message.state, 'sent')
        self.assertFalse(message.hold_until)
        self.room.quiet_enabled = False

    def test_two_identical_sends_both_go_out(self):
        """Unlike an event, which may be replayed, pressing Send twice means
        it twice - so manual keys must never collide."""
        for _index in range(2):
            self.env['midvex.notification.compose'].create({
                'account_id': self.account.id,
                'recipient_ids': [(6, 0, self.room.ids)],
                'body': 'Same text',
            }).action_send()
        messages = self.env['midvex.notification.message'].search([('body', '=', 'Same text')])
        self.assertEqual(len(messages), 2)
        self.assertEqual(len(set(messages.mapped('idempotency_key'))), 2)

    def test_sending_with_no_recipient_is_refused(self):
        wizard = self.env['midvex.notification.compose'].create({
            'account_id': self.account.id, 'body': 'Nowhere',
        })
        with self.assertRaises(UserError):
            wizard.action_send()

    def test_it_writes_to_the_originating_record_chatter(self):
        partner = self.env['res.partner'].create({'name': 'Chatter Co'})
        before = len(partner.message_ids)
        wizard = self.env['midvex.notification.compose'].create({
            'account_id': self.account.id,
            'recipient_ids': [(6, 0, self.room.ids)],
            'body': 'About this partner',
            'res_model': 'res.partner', 'res_id': partner.id,
        })
        wizard.action_send()
        self.assertEqual(len(partner.message_ids), before + 1)
        self.assertIn('About this partner', partner.message_ids[0].body)

    def test_the_wizard_never_logs_onto_itself(self):
        """active_model is set on any action opened from a view, including this
        wizard's own menu entry, where it points at the transient record."""
        composer = self.env['midvex.notification.compose'].with_context(
            active_model='midvex.notification.compose', active_id=1)
        values = composer.default_get(['res_model', 'res_id'])
        self.assertFalse(values.get('res_model'))

    def test_switching_account_clears_recipients(self):
        """Recipients belong to one account; carrying them over would send to
        a chat id the new bot has never seen."""
        other = self.env['midvex.notification.account'].create({
            'name': 'Other account', 'channel_id': self.channel.id, 'state': 'connected',
        })
        wizard = self.env['midvex.notification.compose'].create({
            'account_id': self.account.id,
            'recipient_ids': [(6, 0, self.room.ids)],
            'body': 'x',
        })
        wizard.account_id = other
        wizard._onchange_account_id()
        self.assertFalse(wizard.recipient_ids)
