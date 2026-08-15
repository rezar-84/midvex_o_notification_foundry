from odoo.exceptions import UserError
from odoo.tests.common import TransactionCase

from odoo.addons.midvex_o_notification_foundry.tests.common import ensure_channel

from . import fixtures


class TestWhatsAppSettingsPanel(TransactionCase):
    """Credentials in Settings, without losing company scoping.

    The panel is a second door onto the account, not a second store. Everything
    below is about that staying true: what it resolves, what it writes, and
    what it refuses to show.
    """

    def setUp(self):
        super().setUp()
        self.channel = ensure_channel(self.env, 'whatsapp', 'WhatsApp')
        self.company_a = self.env['res.company'].create({'name': 'Settings Co A'})
        self.company_b = self.env['res.company'].create({'name': 'Settings Co B'})
        self.account_a = self.env['midvex.notification.account'].create({
            'name': 'WA A', 'channel_id': self.channel.id,
            'company_id': self.company_a.id, 'wa_phone_number_id': fixtures.PHONE_NUMBER_ID,
        })
        self.account_b = self.env['midvex.notification.account'].create({
            'name': 'WA B', 'channel_id': self.channel.id,
            'company_id': self.company_b.id, 'wa_phone_number_id': '400000000000004',
        })

    def settings(self, company):
        return self.env['res.config.settings'].with_company(company).create({})

    # --- resolution ----------------------------------------------------

    def test_it_resolves_the_current_companys_account(self):
        self.assertEqual(self.settings(self.company_a).wa_account_id, self.account_a)
        self.assertEqual(self.settings(self.company_b).wa_account_id, self.account_b)

    def test_it_never_falls_back_to_another_companys_account(self):
        """"The first WhatsApp account in the database" would show one company's
        credentials to another the moment a second number is onboarded."""
        third = self.env['res.company'].create({'name': 'Settings Co C'})
        settings = self.settings(third)
        self.assertFalse(settings.wa_account_id)
        self.assertFalse(settings.wa_has_account)

    def test_an_archived_account_is_still_found(self):
        """Otherwise archiving one silently offers to create a duplicate."""
        self.account_a.active = False
        self.assertEqual(self.settings(self.company_a).wa_account_id, self.account_a)

    def test_a_telegram_account_is_not_offered_as_a_whatsapp_one(self):
        telegram = ensure_channel(self.env, 'telegram', 'Telegram')
        third = self.env['res.company'].create({'name': 'Settings Co D'})
        self.env['midvex.notification.account'].create({
            'name': 'TG', 'channel_id': telegram.id, 'company_id': third.id,
        })
        self.assertFalse(self.settings(third).wa_has_account)

    # --- write-through -------------------------------------------------

    def test_credentials_written_here_reach_the_account(self):
        settings = self.settings(self.company_a)
        settings.write({
            'wa_api_key': 'TOKEN-PLACEHOLDER',
            'wa_api_secret': 'SECRET-PLACEHOLDER',
            'wa_webhook_secret': 'VERIFY-PLACEHOLDER',
        })
        self.account_a.invalidate_recordset()
        self.assertEqual(self.account_a.api_key, 'TOKEN-PLACEHOLDER')
        self.assertEqual(self.account_a.api_secret, 'SECRET-PLACEHOLDER')
        self.assertEqual(self.account_a.webhook_secret, 'VERIFY-PLACEHOLDER')

    def test_identifiers_written_here_reach_the_account(self):
        settings = self.settings(self.company_a)
        settings.write({
            'wa_business_account_id': fixtures.WABA_ID,
            'wa_display_number': '+90 500 000 0000',
            'wa_api_version': 'v26.0',
            'wa_test_mode': True,
        })
        self.account_a.invalidate_recordset()
        self.assertEqual(self.account_a.wa_business_account_id, fixtures.WABA_ID)
        self.assertEqual(self.account_a.wa_api_version, 'v26.0')
        self.assertTrue(self.account_a.wa_test_mode)

    def test_writing_one_companys_panel_leaves_the_other_alone(self):
        """The failure this whole design exists to prevent."""
        self.settings(self.company_a).write({'wa_api_key': 'A-ONLY'})
        self.account_b.invalidate_recordset()
        self.assertFalse(self.account_b.api_key)

    # --- status --------------------------------------------------------

    def test_the_callback_url_names_this_companys_account(self):
        settings = self.settings(self.company_a)
        self.assertTrue(
            settings.wa_callback_url.endswith(
                '/notification/whatsapp/webhook/%s' % self.account_a.id))

    def test_a_non_https_base_url_is_flagged(self):
        """Meta refuses plain HTTP, and finding that out from Meta is slower
        than being told here."""
        self.env['ir.config_parameter'].sudo().set_param(
            'web.base.url', 'http://localhost:8069')
        self.assertFalse(self.settings(self.company_a).wa_callback_is_https)
        self.env['ir.config_parameter'].sudo().set_param(
            'web.base.url', 'https://erp.example.com')
        self.assertTrue(self.settings(self.company_a).wa_callback_is_https)

    def test_the_release_api_version_is_shown_for_comparison(self):
        from ..services.whatsapp_client import DEFAULT_API_VERSION
        self.assertEqual(
            self.settings(self.company_a).wa_default_api_version, DEFAULT_API_VERSION)

    def test_the_template_count_is_scoped_to_this_account(self):
        self.env['midvex.notification.whatsapp.template'].create({
            'account_id': self.account_a.id, 'template_code': 'lead_created',
            'language_code': 'en_US', 'provider_template_name': 'a_tpl',
        })
        self.assertEqual(self.settings(self.company_a).wa_template_count, 1)
        self.assertEqual(self.settings(self.company_b).wa_template_count, 0)

    # --- actions -------------------------------------------------------

    def test_testing_a_connection_with_no_account_says_so(self):
        third = self.env['res.company'].create({'name': 'Settings Co E'})
        with self.assertRaises(UserError):
            self.settings(third).action_wa_test_connection()

    def test_creating_an_account_makes_one_for_this_company(self):
        third = self.env['res.company'].create({'name': 'Settings Co F'})
        settings = self.settings(third)
        action = settings.action_wa_create_account()
        created = self.env['midvex.notification.account'].browse(action['res_id'])
        self.assertEqual(created.company_id, third)
        self.assertEqual(created.channel_code, 'whatsapp')

    def test_a_created_account_satisfies_the_phone_number_constraint(self):
        """The model requires a phone number ID, and the button cannot know it.

        A placeholder that is obviously a placeholder beats either a crash or a
        blank that looks configured.
        """
        third = self.env['res.company'].create({'name': 'Settings Co G'})
        action = self.settings(third).action_wa_create_account()
        created = self.env['midvex.notification.account'].browse(action['res_id'])
        self.assertTrue(created.wa_phone_number_id)
        self.assertIn('CHANGE', created.wa_phone_number_id.upper())
