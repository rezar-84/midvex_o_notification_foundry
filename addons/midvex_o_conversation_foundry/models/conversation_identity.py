from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class ConversationIdentity(models.Model):
    """How one person is addressed on one channel.

    A customer is a `res.partner` to Odoo and a phone number to WhatsApp, a
    chat id to Telegram, an opaque token to the web widget. This is the join,
    and it is what lets a thread survive the customer switching channel.

    Deliberately not a field on res.partner. One person has many identities —
    two numbers, a Telegram account, a browser session that later turns out to
    be them — and they arrive before we know who they are. An identity exists
    from the first inbound message; `partner_id` is filled in when, and if,
    somebody works out who is on the other end.
    """

    _name = 'midvex.conversation.identity'
    _description = 'Conversation Identity'
    _order = 'last_seen_at desc, id desc'
    _rec_name = 'display_identifier'

    identity_type = fields.Selection(
        [('whatsapp', 'WhatsApp'), ('telegram', 'Telegram'),
         ('email', 'Email'), ('web', 'Web Chat')],
        required=True, index=True)
    normalized_identifier = fields.Char(
        required=True, index=True,
        help='The canonical form used for matching — E.164 for a phone number. Two '
             'spellings of one address must normalize to one value here or one person '
             'becomes two customers.')
    display_identifier = fields.Char(
        help='The address as the provider or the person themselves writes it. Shown to '
             'agents; never matched on.')
    provider_identifier = fields.Char(
        help="The provider's own opaque id for this person, where it has one distinct "
             'from the address.')
    partner_id = fields.Many2one(
        'res.partner', ondelete='set null', index=True,
        help='Filled in once somebody knows who this is. Empty is the normal state for '
             'a first-time enquiry, not an error.')
    # Company-scoped rather than global. The same phone number contacting two
    # companies in the group is two relationships, and the record rules below
    # are what keep one company's customer list out of the other's.
    company_id = fields.Many2one(
        'res.company', required=True, index=True,
        default=lambda self: self.env.company)
    verified = fields.Boolean(
        default=False,
        help='Set when the person proved they control this address — replied from it, '
             'or completed a channel linking flow. An unverified identity is a claim.')
    verification_source = fields.Char()
    first_seen_at = fields.Datetime(readonly=True, default=fields.Datetime.now)
    last_seen_at = fields.Datetime(readonly=True, default=fields.Datetime.now)
    thread_ids = fields.One2many('midvex.conversation.thread', 'identity_id')
    active = fields.Boolean(default=True)

    _identity_uniq = models.Constraint(
        'UNIQUE (company_id, identity_type, normalized_identifier)',
        'This identity already exists for this company.')

    @api.depends('display_identifier', 'normalized_identifier', 'partner_id')
    def _compute_display_name(self):
        for identity in self:
            address = identity.display_identifier or identity.normalized_identifier
            identity.display_name = (
                '%s (%s)' % (identity.partner_id.name, address)
                if identity.partner_id else address or _('Unknown'))

    @api.constrains('normalized_identifier')
    def _check_normalized_identifier(self):
        for identity in self:
            if not (identity.normalized_identifier or '').strip():
                raise ValidationError(_('An identity needs a normalized identifier.'))

    @api.model
    def find_or_create(self, company, identity_type, normalized_identifier,
                       display_identifier=None, provider_identifier=None):
        """The identity for this address, creating it the first time.

        Matching is on the normalized value alone — never on a display name,
        which the person controls and changes. Telegram usernames in particular
        are mutable, so a match on one would silently reassign a conversation
        the day somebody renamed themselves.
        """
        if not normalized_identifier:
            raise ValidationError(_('Cannot identify a party without an identifier.'))

        domain = [
            ('company_id', '=', company.id),
            ('identity_type', '=', identity_type),
            ('normalized_identifier', '=', normalized_identifier),
        ]
        identity = self.sudo().with_context(active_test=False).search(domain, limit=1)
        if identity:
            values = {'last_seen_at': fields.Datetime.now()}
            # An archived identity coming back is the same person returning,
            # not a new one. Reviving beats creating a duplicate the unique
            # constraint would refuse anyway.
            if not identity.active:
                values['active'] = True
            if display_identifier and not identity.display_identifier:
                values['display_identifier'] = display_identifier
            identity.write(values)
            return identity

        return self.sudo().create({
            'company_id': company.id,
            'identity_type': identity_type,
            'normalized_identifier': normalized_identifier,
            'display_identifier': display_identifier or normalized_identifier,
            'provider_identifier': provider_identifier,
        })

    def action_link_partner(self, partner):
        """Attach this identity to a known contact.

        Kept as a method rather than left to a form write so that linking is
        one auditable act — phase 4's CRM bridge will want to react to it, and
        a bare field write gives it nothing to hook.
        """
        self.ensure_one()
        self.write({'partner_id': partner.id, 'verified': True,
                    'verification_source': 'manual'})
        return True
