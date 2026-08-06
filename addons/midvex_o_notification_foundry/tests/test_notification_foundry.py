from odoo.tests.common import TransactionCase
from odoo.exceptions import AccessError

from .common import ensure_channel


class TestNotificationFoundry(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.channel = ensure_channel(cls.env, 'dummy')
        cls.account = cls.env['midvex.notification.account'].create({
            'name': 'Test account', 'channel_id': cls.channel.id, 'state': 'connected',
        })
        cls.other_user = cls.env['res.users'].create({
            'name': 'Other User', 'login': 'notif_other_user', 'email': 'other@example.com',
        })

    def test_channel_code_is_unique(self):
        with self.assertRaises(Exception):
            self.env['midvex.notification.channel'].create({'name': 'Dummy 2', 'code': 'dummy'})

    def test_recipient_is_unique_per_account_and_user(self):
        self.env['midvex.notification.recipient'].create({'user_id': self.env.user.id, 'account_id': self.account.id})
        with self.assertRaises(Exception):
            self.env['midvex.notification.recipient'].create({'user_id': self.env.user.id, 'account_id': self.account.id})

    def test_user_cannot_generate_link_code_for_another_users_recipient(self):
        recipient = self.env['midvex.notification.recipient'].create({
            'user_id': self.other_user.id, 'account_id': self.account.id,
        })
        recipient_as_self = recipient.with_user(self.env.user)
        with self.assertRaises(AccessError):
            recipient_as_self.action_generate_link_code()

    def test_manager_can_generate_link_code_for_any_recipient(self):
        self.env.user.group_ids |= self.env.ref('midvex_o_notification_foundry.group_notification_manager')
        recipient = self.env['midvex.notification.recipient'].create({
            'user_id': self.other_user.id, 'account_id': self.account.id,
        })
        recipient.action_generate_link_code()
        self.assertTrue(recipient.link_code)
