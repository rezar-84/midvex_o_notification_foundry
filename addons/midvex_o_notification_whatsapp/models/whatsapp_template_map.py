from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class WhatsAppTemplateMap(models.Model):
    """Maps one of the foundry's semantic templates onto an approved provider template.

    WhatsApp will not deliver a business-initiated message as free text once the
    24-hour customer service window has closed — it rejects it with error
    131047. The message has to be a template that Meta approved in advance, by
    name, in a specific language.

    So the foundry's template ("lead_created", a body with {{ object.name }} in
    it) and the provider's template ("vars_lead_created" in en_US, approved,
    with two positional variables) are different objects that happen to say the
    same thing, and something has to hold the correspondence. This is it.

    Approval status is not synced. Meta has an API for it, and until the list is
    long enough to be a burden, a name typed in by whoever got it approved is
    both simpler and more honest — a stale synced "APPROVED" flag is worse than
    no flag.
    """

    _name = 'midvex.notification.whatsapp.template'
    _description = 'WhatsApp Template Mapping'
    _order = 'template_code, language_code'
    _check_company_auto = True

    account_id = fields.Many2one(
        'midvex.notification.account', required=True, ondelete='cascade', index=True,
        domain="[('channel_code', '=', 'whatsapp')]")
    company_id = fields.Many2one(related='account_id.company_id', store=True, index=True)
    template_id = fields.Many2one(
        'midvex.notification.template', ondelete='cascade',
        help='The foundry template this stands in for. Optional: a provider template can '
             'be mapped by code alone, for rules whose template was created elsewhere.')
    template_code = fields.Char(
        required=True, index=True,
        help="The foundry template's code, e.g. lead_created.")
    language_code = fields.Char(
        required=True, default='en_US',
        help='Meta language and locale code, e.g. en_US or tr_TR. A template approved in '
             'one language cannot be sent as another — they are separate approvals.')
    provider_template_name = fields.Char(
        required=True,
        help='The template name exactly as approved in the Meta App Dashboard.')
    provider_category = fields.Selection(
        [('utility', 'Utility'), ('marketing', 'Marketing'), ('authentication', 'Authentication')],
        default='utility',
        help='Meta categorises templates and prices them differently. Ordinary '
             'transactional notifications are Utility.')
    provider_status = fields.Selection(
        [('draft', 'Draft'), ('pending', 'Pending Approval'), ('approved', 'Approved'),
         ('rejected', 'Rejected'), ('paused', 'Paused')],
        default='pending',
        help='Recorded by hand. Not synced from Meta — a stale approval flag would be '
             'worse than none.')
    body_variable_fields = fields.Char(
        string='Body Variables',
        help='Comma-separated names of message DTO keys, in the order the approved '
             'template expects them, e.g. "subject,body". Leave empty for a template '
             'with no variables.')
    active = fields.Boolean(default=True)

    _template_language_uniq = models.Constraint(
        'UNIQUE (account_id, template_code, language_code)',
        'This account already maps that template for that language.')

    @api.constrains('language_code')
    def _check_language_code(self):
        for mapping in self:
            if not (mapping.language_code or '').strip():
                raise ValidationError(_('A template mapping needs a language code.'))

    @api.model
    def find_for(self, account, template_code, lang=None):
        """The mapping to use, or an empty recordset when the message is free text.

        Language matching is deliberately forgiving in one direction only. Odoo
        writes languages as "tr_TR" and Meta accepts the same shape, but an Odoo
        user's lang can be "tr_TR" where the template was approved as "tr", or
        the reverse. Falling back on the base language finds the approval that
        exists; falling back on *any* language would send a Turkish customer an
        English template, which is worse than sending nothing and is exactly
        what ADR-011 was written to stop.
        """
        if not account or not template_code:
            return self.browse()

        domain = [('account_id', '=', account.id), ('template_code', '=', template_code),
                  ('active', '=', True)]
        candidates = self.search(domain)
        if not candidates:
            return self.browse()

        wanted = (lang or '').replace('-', '_')
        for candidate in candidates:
            if candidate.language_code == wanted:
                return candidate

        base = wanted.split('_')[0]
        if base:
            for candidate in candidates:
                if candidate.language_code.split('_')[0] == base:
                    return candidate

        return self.browse()

    def build_component_payload(self, message_dto):
        """The `template` object for the send payload.

        Variables are read positionally out of the message DTO, in the order
        named by body_variable_fields, because that is how Meta's approved
        templates address them — {{1}}, {{2}} — and there is no named form.

        A missing key becomes an empty string rather than raising: a template
        variable that came out blank produces a slightly worse message, and a
        traceback in the queue cron produces none at all.
        """
        self.ensure_one()
        template = {
            'name': self.provider_template_name,
            'language': {'code': self.language_code},
        }
        names = [name.strip() for name in (self.body_variable_fields or '').split(',')
                 if name.strip()]
        if names:
            template['components'] = [{
                'type': 'body',
                'parameters': [
                    {'type': 'text', 'text': str(message_dto.get(name) or '')}
                    for name in names
                ],
            }]
        return template
