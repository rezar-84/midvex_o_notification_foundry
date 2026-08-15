from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class ConversationSession(models.Model):
    """One channel's leg of a thread.

    A thread is the conversation; a session is how it is being carried right
    now. The customer who started on the website widget and continued on
    WhatsApp has one thread and two sessions, which is why the account, the
    channel code and the provider's own address live here rather than up there.

    It is also where the company invariant is actually enforceable, because the
    session is the only record that touches both the thread and the channel
    account.
    """

    _name = 'midvex.conversation.session'
    _description = 'Conversation Session'
    _order = 'last_activity_at desc, id desc'
    _check_company_auto = True

    thread_id = fields.Many2one(
        'midvex.conversation.thread', required=True, ondelete='cascade', index=True)
    company_id = fields.Many2one(
        related='thread_id.company_id', store=True, index=True,
        help='Always the thread\'s. Derived rather than set so the two cannot drift.')
    channel_code = fields.Char(required=True, index=True)
    account_id = fields.Many2one(
        'midvex.notification.account', required=True, ondelete='restrict', index=True,
        help='The channel account this leg speaks through — the same shared registry '
             'the notification foundry uses.')
    external_session_id = fields.Char(
        help="The provider's own conversation id, where it has one.")
    external_recipient_id = fields.Char(
        required=True, index=True,
        help='The address to reply to on this channel. Copied onto every outbound '
             'delivery job, so it is what the provider actually receives.')
    state = fields.Selection(
        [('open', 'Open'), ('closed', 'Closed')], default='open', required=True, index=True)
    opened_at = fields.Datetime(readonly=True, default=fields.Datetime.now)
    last_activity_at = fields.Datetime(readonly=True, default=fields.Datetime.now)
    closed_at = fields.Datetime(readonly=True)
    message_ids = fields.One2many('midvex.conversation.message', 'session_id')
    metadata_json = fields.Json(
        help='Channel-specific state that does not deserve a column — a web widget\'s '
             'token expiry, a provider conversation window. Never business data.')

    @api.constrains('thread_id', 'account_id')
    def _check_company_invariant(self):
        """thread.company_id == session.company_id == account.company_id.

        The rule the whole security model rests on, and the one the source pack
        singles out as having to fail server-side rather than be filtered in a
        view. Violated, a company's branded number sends on another company's
        behalf — which is not a permissions bug the customer can see, it is the
        wrong business writing to them.
        """
        for session in self:
            account_company = session.account_id.sudo().company_id
            if account_company != session.thread_id.company_id:
                raise ValidationError(_(
                    'This conversation belongs to %(thread)s but the channel account '
                    'belongs to %(account)s. A conversation cannot send through '
                    'another company\'s account.',
                    thread=session.thread_id.company_id.display_name,
                    account=account_company.display_name))

    @api.constrains('channel_code', 'account_id')
    def _check_channel_matches_account(self):
        """A WhatsApp session cannot hang off a Telegram account.

        Left unchecked this fails much later and much more confusingly: the
        session looks right, and the send fails at the adapter with a payload
        the channel does not recognise.
        """
        for session in self:
            account_code = session.account_id.sudo().channel_code
            if account_code and session.channel_code != account_code:
                raise ValidationError(_(
                    'A %(session)s session cannot use a %(account)s account.',
                    session=session.channel_code, account=account_code))

    def action_close(self):
        for session in self:
            session.write({'state': 'closed', 'closed_at': fields.Datetime.now()})
        return True

    def _touch(self, when=None):
        self.ensure_one()
        self.write({'last_activity_at': when or fields.Datetime.now()})
        return True
