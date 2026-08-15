from odoo import _, api, fields, models
from odoo.exceptions import UserError

from ..services.whatsapp_client import DEFAULT_API_VERSION


class ResConfigSettings(models.TransientModel):
    """WhatsApp credentials and status, in Settings.

    The account record remains the source of truth — this is a second door onto
    it, not a second store. That distinction matters more than it sounds:
    credentials are per company (ADR-004 gives each its own branded number), so
    a genuinely global settings page would either hold one company's secrets
    for everyone or quietly overwrite the wrong account.

    So the panel is scoped to **the current company's** WhatsApp account. Switch
    company in the top bar and the fields follow. If that company has no account
    yet, the panel says so and offers to create one rather than silently
    editing another company's.
    """

    _inherit = 'res.config.settings'

    wa_account_id = fields.Many2one(
        'midvex.notification.account', string='WhatsApp Account',
        compute='_compute_wa_account_id', store=False, readonly=True,
        help='The WhatsApp account for the company you are currently in.')
    wa_has_account = fields.Boolean(compute='_compute_wa_account_id')

    # Credentials. Related through the account so this writes to the one place
    # they live; `readonly=False` is what makes a related field writable.
    wa_api_key = fields.Char(
        related='wa_account_id.api_key', readonly=False, string='Access Token',
        groups='midvex_o_notification_foundry.group_notification_admin')
    wa_api_secret = fields.Char(
        related='wa_account_id.api_secret', readonly=False, string='App Secret',
        groups='midvex_o_notification_foundry.group_notification_admin')
    wa_webhook_secret = fields.Char(
        related='wa_account_id.webhook_secret', readonly=False, string='Verify Token',
        groups='midvex_o_notification_foundry.group_notification_admin')

    # Identifiers.
    wa_business_account_id = fields.Char(
        related='wa_account_id.wa_business_account_id', readonly=False,
        string='WhatsApp Business Account ID')
    wa_phone_number_id = fields.Char(
        related='wa_account_id.wa_phone_number_id', readonly=False,
        string='Phone Number ID')
    wa_display_number = fields.Char(
        related='wa_account_id.wa_display_number', readonly=False,
        string='Display Number')
    wa_api_version = fields.Char(
        related='wa_account_id.wa_api_version', readonly=False,
        string='Graph API Version')
    wa_test_mode = fields.Boolean(
        related='wa_account_id.wa_test_mode', readonly=False, string='Test Mode')

    # Status, read-only. What somebody opening Settings actually wants to know
    # before they touch anything: is this working, and when did it last work.
    wa_state = fields.Selection(related='wa_account_id.state', readonly=True,
                                 string='Connection')
    wa_last_test_at = fields.Datetime(related='wa_account_id.last_test_at', readonly=True,
                                       string='Last Tested')
    wa_last_error = fields.Text(related='wa_account_id.last_error', readonly=True,
                                 string='Last Error')
    wa_callback_url = fields.Char(compute='_compute_wa_callback_url', readonly=True,
                                   string='Callback URL')
    wa_callback_is_https = fields.Boolean(compute='_compute_wa_callback_url')
    wa_template_count = fields.Integer(compute='_compute_wa_counts',
                                        string='Template Mappings')
    wa_default_api_version = fields.Char(
        compute='_compute_wa_default_api_version',
        string='Version This Release Was Written Against')

    @api.depends_context('company')
    def _compute_wa_account_id(self):
        """The current company's WhatsApp account, if it has one.

        Deliberately not "the first WhatsApp account in the database": that
        would show one company's credentials to another the moment a second
        number is onboarded, which is the exact failure ADR-004 and the record
        rules exist to prevent.
        """
        for settings in self:
            # active_test off, and an active-first ordering: an archived account
            # is still this company's account. Filtered out, Settings would
            # report there is none and offer to create a second — leaving two
            # accounts for one number, one of them holding the credentials.
            account = self.env['midvex.notification.account'].with_context(
                active_test=False).search([
                    ('channel_code', '=', 'whatsapp'),
                    ('company_id', '=', self.env.company.id),
                ], order='active desc, id', limit=1)
            settings.wa_account_id = account
            settings.wa_has_account = bool(account)

    @api.depends('wa_account_id')
    def _compute_wa_callback_url(self):
        base_url = self.env['ir.config_parameter'].sudo().get_param('web.base.url') or ''
        for settings in self:
            if settings.wa_account_id:
                settings.wa_callback_url = '%s/notification/whatsapp/webhook/%s' % (
                    base_url.rstrip('/'), settings.wa_account_id.id)
            else:
                settings.wa_callback_url = False
            settings.wa_callback_is_https = base_url.startswith('https://')

    @api.depends('wa_account_id')
    def _compute_wa_counts(self):
        Template = self.env['midvex.notification.whatsapp.template']
        for settings in self:
            settings.wa_template_count = Template.search_count(
                [('account_id', '=', settings.wa_account_id.id)]
            ) if settings.wa_account_id else 0

    def _compute_wa_default_api_version(self):
        # Shown beside the account's own version so a drift is visible. The
        # account may legitimately be pinned elsewhere; what is unhelpful is
        # not knowing.
        for settings in self:
            settings.wa_default_api_version = DEFAULT_API_VERSION

    # --- actions -------------------------------------------------------

    def action_wa_create_account(self):
        """Create the current company's WhatsApp account and open it.

        Offered rather than done implicitly. An account is a real record with a
        company and a channel, and conjuring one as a side effect of opening
        Settings is how a database ends up with accounts nobody meant to make.
        """
        self.ensure_one()
        channel = self.env.ref('midvex_o_notification_whatsapp.channel_whatsapp',
                                raise_if_not_found=False)
        if not channel:
            raise UserError(_('The WhatsApp channel record is missing. Upgrade the '
                              'module and try again.'))
        account = self.env['midvex.notification.account'].create({
            'name': _('WhatsApp — %s', self.env.company.name),
            'channel_id': channel.id,
            'company_id': self.env.company.id,
            # Placeholder, because the model requires one and the whole point of
            # this button is that the real value is not known yet. It is the
            # first thing the form asks for.
            'wa_phone_number_id': 'CHANGE-ME',
        })
        return {
            'type': 'ir.actions.act_window',
            'name': _('WhatsApp Account'),
            'res_model': 'midvex.notification.account',
            'res_id': account.id,
            'view_mode': 'form',
            'target': 'current',
        }

    def action_wa_test_connection(self):
        """Read the phone number node. Messages nobody, so it is safe to press."""
        self.ensure_one()
        if not self.wa_account_id:
            raise UserError(_('There is no WhatsApp account for this company yet.'))
        return self.wa_account_id.action_test_connection()

    def action_wa_open_account(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('WhatsApp Account'),
            'res_model': 'midvex.notification.account',
            'res_id': self.wa_account_id.id,
            'view_mode': 'form',
            'target': 'current',
        }

    def action_wa_open_templates(self):
        self.ensure_one()
        action = self.env['ir.actions.act_window']._for_xml_id(
            'midvex_o_notification_whatsapp.action_whatsapp_template')
        action['domain'] = [('account_id', '=', self.wa_account_id.id)]
        action['context'] = {'default_account_id': self.wa_account_id.id}
        return action
