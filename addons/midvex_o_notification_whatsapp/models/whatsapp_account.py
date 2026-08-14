from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

from ..services.whatsapp_client import DEFAULT_API_VERSION


class NotificationAccount(models.Model):
    """WhatsApp configuration on the shared notification account.

    Deliberately an extension rather than a second account model. The foundry
    hands adapters an account; a WhatsApp-only account model would mean the
    dispatcher, the recipient links, the message queue and the record rules all
    needing to know which kind they were looking at.

    The three credentials reuse the fields that already exist and are already
    gated on group_notification_admin:

        api_key        -> System User access token
        api_secret     -> app secret, the webhook signature key
        webhook_secret -> webhook verify token

    That reuse is not laziness. A new secret field means new masking, new ACL
    rows, and a new way to leak; these three already have all of it.
    """

    _inherit = 'midvex.notification.account'

    wa_business_account_id = fields.Char(
        string='WhatsApp Business Account ID',
        help='The WABA ID from the Meta App Dashboard. Inbound webhook payloads carry it '
             'as entry[].id.')
    wa_phone_number_id = fields.Char(
        string='Phone Number ID',
        help='The business phone number ID from the Meta App Dashboard. This is the ID '
             'used in API calls, not the phone number itself.')
    wa_display_number = fields.Char(
        string='Display Number',
        help='The number customers see. Informational only; API calls use the phone '
             'number ID.')
    wa_api_version = fields.Char(
        string='Graph API Version', default=DEFAULT_API_VERSION,
        help='Pinned rather than tracking latest, so a provider release cannot change '
             'behaviour without a decision. Moving version is a change here, not a code '
             'release.')
    wa_test_mode = fields.Boolean(
        string='Test Mode',
        help='Marks this account as pointing at a test number. Does not change how '
             'messages are sent — it exists so a production number is never mistaken '
             'for a sandbox one in the account list.')
    wa_template_ids = fields.One2many(
        'midvex.notification.whatsapp.template', 'account_id', string='Template Mappings')

    @api.constrains('channel_code', 'wa_phone_number_id')
    def _check_whatsapp_phone_number_id(self):
        """A WhatsApp account without a phone number ID cannot send anything.

        Caught here rather than at send time because the failure is silent
        until a real alert needs to go out, and by then it is a customer who
        did not hear back. The same class of mistake as the live account whose
        channel code was '1'.
        """
        for account in self:
            if account.channel_code == 'whatsapp' and not account.wa_phone_number_id:
                raise ValidationError(_(
                    'A WhatsApp account needs its Phone Number ID. Without it no message '
                    'can be sent and no webhook can be matched to this account.'))

    def action_whatsapp_webhook_url(self):
        """Show the callback URL and verify token to paste into the App Dashboard.

        Meta has no setWebhook, so this is a copy-and-paste step by hand. Making
        the exact URL visible in Odoo beats having somebody assemble it from the
        route and hope the base URL matches.
        """
        self.ensure_one()
        base_url = self.env['ir.config_parameter'].sudo().get_param('web.base.url') or ''
        url = '%s/notification/whatsapp/webhook/%s' % (base_url.rstrip('/'), self.id)
        if not base_url.startswith('https://'):
            message = _(
                'Callback URL: %s\n\nMeta requires HTTPS and will refuse this URL. Set '
                "web.base.url to the instance's public HTTPS address first.", url)
        else:
            message = _(
                'Callback URL: %s\n\nPaste this into the Meta App Dashboard under '
                'WhatsApp > Configuration, with the account\'s Verify Token, then '
                'subscribe the WhatsApp Business Account to the "messages" field.', url)
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'type': 'info',
                'title': _('WhatsApp webhook'),
                'message': message,
                'sticky': True,
            },
        }
