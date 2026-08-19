from odoo.tests.common import TransactionCase
from odoo.exceptions import UserError
from .common import ensure_channel


class TestMultiCompanyIsolation(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company_a = cls.env.company
        cls.company_b = cls.env['res.company'].create({'name': 'Company B'})

        cls.channel = ensure_channel(cls.env, 'dummy')

        cls.account_a = cls.env['midvex.notification.account'].create({
            'name': 'Bot Company A',
            'channel_id': cls.channel.id,
            'company_id': cls.company_a.id,
            'state': 'connected',
        })
        cls.account_b = cls.env['midvex.notification.account'].create({
            'name': 'Bot Company B',
            'channel_id': cls.channel.id,
            'company_id': cls.company_b.id,
            'state': 'connected',
        })

        cls.user = cls.env['res.users'].create({
            'name': 'Multi Comp User',
            'login': 'multicomp_user',
            'email': 'multicomp@example.com',
            'company_id': cls.company_a.id,
            'company_ids': [(6, 0, [cls.company_a.id, cls.company_b.id])],
            'group_ids': [(4, cls.env.ref('midvex_o_notification_foundry.group_notification_user').id)],
        })

    def test_get_or_create_link_respects_active_company(self):
        # User active company = Company A
        rec_a = self.env['midvex.notification.recipient'].with_user(self.user).with_context(
            allowed_company_ids=[self.company_a.id]).get_or_create_link(self.user, 'dummy')
        self.assertEqual(rec_a.account_id, self.account_a)
        self.assertEqual(rec_a.company_id, self.company_a)

        # Switch active company to Company B
        rec_b = self.env['midvex.notification.recipient'].with_user(self.user).with_context(
            allowed_company_ids=[self.company_b.id]).with_env(
            self.env(user=self.user, context={'allowed_company_ids': [self.company_b.id]})).get_or_create_link(self.user, 'dummy')
        self.assertEqual(rec_b.account_id, self.account_b)
        self.assertEqual(rec_b.company_id, self.company_b)
        self.assertNotEqual(rec_a, rec_b)

    def test_process_link_code_scoped_to_account(self):
        Recipient = self.env['midvex.notification.recipient'].with_user(self.user)
        rec_a = Recipient.with_context(allowed_company_ids=[self.company_a.id]).get_or_create_link(self.user, 'dummy')
        code = rec_a.link_code
        self.assertTrue(code)

        # Trying to redeem code against Bot B should fail
        redeemed_b = Recipient.process_link_code(code, 'ext_123', account=self.account_b)
        self.assertFalse(redeemed_b)

        # Redeeming against Bot A should succeed
        redeemed_a = Recipient.process_link_code(code, 'ext_123', account=self.account_a)
        self.assertEqual(redeemed_a, rec_a)
        self.assertEqual(rec_a.state, 'linked')

    def test_dispatcher_multi_company_isolation(self):
        from ..services.dispatcher import _targets

        # Link user to account A and account B
        Recipient = self.env['midvex.notification.recipient']
        rec_a = Recipient.create({
            'user_id': self.user.id,
            'account_id': self.account_a.id,
            'external_id': '111',
            'state': 'linked',
        })
        rec_b = Recipient.create({
            'user_id': self.user.id,
            'account_id': self.account_b.id,
            'external_id': '222',
            'state': 'linked',
        })

        # When targeting account A, targets must yield only rec_a
        targets_a = list(_targets(Recipient, self.env['midvex.notification.rule'], [self.user], self.channel, account=self.account_a))
        self.assertEqual(len(targets_a), 1)
        self.assertEqual(targets_a[0][0], rec_a)

        # When targeting account B, targets must yield only rec_b
        targets_b = list(_targets(Recipient, self.env['midvex.notification.rule'], [self.user], self.channel, account=self.account_b))
        self.assertEqual(len(targets_b), 1)
        self.assertEqual(targets_b[0][0], rec_b)
