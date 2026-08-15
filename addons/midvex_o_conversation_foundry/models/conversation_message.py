from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

#: Delivery states, weakest to strongest. Providers do not deliver these in
#: order — WhatsApp routinely reports `read` before `delivered` — so the ladder
#: only ever climbs.
DELIVERY_RANK = {
    'queued': 0,
    'submitted': 1,
    'sent': 2,
    'delivered': 3,
    'read': 4,
}


class ConversationMessage(models.Model):
    """One thing that was said, and stays said.

    Deliberately a different model from `midvex.notification.message`, which is
    a delivery job: a queue row that stops mattering the moment it reads `sent`.
    This is the history — what the customer wrote, what we replied, in what
    order, in whose words. Conflating the two is the specific mistake ADR-013
    exists to prevent, and the giveaway is that one of them can be pruned and
    the other cannot.

    Outbound messages point at their delivery job through `delivery_id`. That
    is the whole coupling between the two foundries: one row, one foreign key,
    no second queue. See ADR-020.
    """

    _name = 'midvex.conversation.message'
    _description = 'Conversation Message'
    _order = 'id'
    _check_company_auto = True

    thread_id = fields.Many2one(
        'midvex.conversation.thread', required=True, ondelete='cascade', index=True)
    session_id = fields.Many2one(
        'midvex.conversation.session', ondelete='restrict', index=True,
        help='Which channel leg carried this. Empty for an internal note, which was '
             'never carried anywhere.')
    company_id = fields.Many2one(related='thread_id.company_id', store=True, index=True)
    direction = fields.Selection(
        [('inbound', 'From Customer'), ('outbound', 'To Customer'),
         ('internal', 'Internal Note'), ('system', 'System')],
        required=True, index=True)
    message_type = fields.Selection(
        [('text', 'Text'), ('template', 'Template'), ('image', 'Image'),
         ('document', 'Document'), ('audio', 'Audio'), ('video', 'Video'),
         ('location', 'Location'), ('interactive', 'Interactive'), ('system', 'System')],
        default='text', required=True)
    body = fields.Text()
    original_language = fields.Char(readonly=True)
    translated_body = fields.Text(
        readonly=True,
        help='Never replaces the body. A translation is our reading of what they said, '
             'and the original is what they actually said.')
    translated_language = fields.Char(readonly=True)
    provider_message_id = fields.Char(
        index=True,
        help="The provider's own id. What an inbound delivery status names, and "
             'nothing else, so it is the only way back to this row.')
    reply_to_message_id = fields.Many2one(
        'midvex.conversation.message', ondelete='set null',
        help='Set when the provider tells us this was a reply to a specific message.')
    state = fields.Selection(
        [('queued', 'Queued'), ('submitted', 'Submitted'), ('sent', 'Sent'),
         ('delivered', 'Delivered'), ('read', 'Read'), ('failed', 'Failed')],
        default='queued', required=True, index=True)
    # The delivery job in the one shared queue. Outbound only — nothing was
    # delivered for a message the customer sent us.
    delivery_id = fields.Many2one(
        'midvex.notification.message', ondelete='set null', index=True,
        string='Delivery Job',
        help='The queue row that carries this to the provider, with the retry, '
             'throttling and delivery logging the notification foundry already does.')
    queued_at = fields.Datetime(readonly=True, default=fields.Datetime.now)
    sent_at = fields.Datetime(readonly=True)
    delivered_at = fields.Datetime(readonly=True)
    read_at = fields.Datetime(readonly=True)
    failed_at = fields.Datetime(readonly=True)
    error_code = fields.Char(readonly=True)
    error_message_safe = fields.Text(
        readonly=True,
        help="Safe to show an agent: the provider's own explanation, never a token, a "
             'header or a stack trace.')
    author_user_id = fields.Many2one(
        'res.users', string='Written By', ondelete='set null', readonly=True,
        help='Empty for anything the customer sent, and for anything automation sent.')
    origin = fields.Selection(
        [('odoo', 'Odoo'), ('frontend', 'Frontend'), ('automation', 'Automation'),
         ('ai', 'AI'), ('provider', 'Provider')],
        default='odoo', required=True,
        help='Where this message came from, which is not the same question as who '
             'wrote it. Required for the audit FR-017 asks for.')
    generated_by_ai = fields.Boolean(default=False, readonly=True)

    _provider_message_uniq = models.Constraint(
        'UNIQUE (session_id, provider_message_id)',
        'This provider message has already been recorded on this session.')

    @api.constrains('session_id', 'thread_id')
    def _check_session_belongs_to_thread(self):
        """A message cannot be filed under one thread and carried by another's leg.

        The kind of mistake a service method makes once, under a rename, and
        which then shows one customer's message inside another's conversation.
        """
        for message in self:
            if message.session_id and message.session_id.thread_id != message.thread_id:
                raise ValidationError(_(
                    'This message belongs to a different conversation than its session.'))

    @api.constrains('direction', 'session_id')
    def _check_outbound_has_a_session(self):
        """Nothing can be sent to a customer without a channel to send it on."""
        for message in self:
            if message.direction in ('inbound', 'outbound') and not message.session_id:
                raise ValidationError(_(
                    'A message to or from a customer needs a session. Only internal '
                    'notes and system entries have none.'))

    def _apply_delivery_state(self, state, when=None):
        """Climb the delivery ladder, never descend it.

        Providers report out of order. Writing whatever arrived last would show
        a message the customer has read as merely delivered — or, if `sent`
        turns up late, as not yet delivered at all.

        Returns whether anything changed, so a caller can avoid logging a
        redelivery as news.
        """
        self.ensure_one()
        rank = DELIVERY_RANK.get(state)
        if rank is None or state == 'failed':
            return False
        if DELIVERY_RANK.get(self.state, 0) >= rank:
            return False

        when = when or fields.Datetime.now()
        values = {'state': state}
        stamp = {'sent': 'sent_at', 'delivered': 'delivered_at', 'read': 'read_at'}.get(state)
        if stamp and not self[stamp]:
            values[stamp] = when
        self.write(values)
        return True

    def _apply_failure(self, error_code=None, safe_message=None, when=None):
        """Terminal, and outside the ladder.

        Failure is not a rung — a message that failed did not get further than
        one that was merely sent, it stopped. Kept separate so the monotonic
        check above cannot be talked into treating it as progress.
        """
        self.ensure_one()
        self.write({
            'state': 'failed',
            'failed_at': when or fields.Datetime.now(),
            'error_code': error_code or False,
            'error_message_safe': safe_message or False,
        })
        return True
