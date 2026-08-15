from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError

#: The lifecycle. `new` is untouched by anyone; `open` means an agent has taken
#: it; the two `waiting_*` states say who the ball is with; `resolved` is done
#: but reopenable; `archived` is done and put away.
STATUSES = [
    ('new', 'New'),
    ('open', 'Open'),
    ('waiting_customer', 'Waiting on Customer'),
    ('waiting_agent', 'Waiting on Agent'),
    ('resolved', 'Resolved'),
    ('archived', 'Archived'),
]

#: States a thread can be in and still receive messages without anyone being
#: surprised. A resolved thread receiving one is not an error — it is a
#: customer replying to something they thought was finished — but it has to
#: reopen rather than quietly append.
LIVE_STATUSES = ('new', 'open', 'waiting_customer', 'waiting_agent')


class ConversationThread(models.Model):
    """One logical conversation with one customer.

    Not one channel's session, and not one message. A thread is the business's
    memory of talking to somebody: it survives them moving from the website
    widget to WhatsApp, it carries the assignment and the status, and it is
    what an agent actually opens.

    The channel-specific parts live in `midvex.conversation.session`, one per
    leg. A thread with two sessions is the same conversation continued
    somewhere else, which is the entire reason these are two models.
    """

    _name = 'midvex.conversation.thread'
    _description = 'Conversation Thread'
    _order = 'last_message_at desc, id desc'
    _check_company_auto = True

    name = fields.Char(required=True, default=lambda self: _('Conversation'))
    company_id = fields.Many2one(
        'res.company', required=True, index=True,
        default=lambda self: self.env.company)
    identity_id = fields.Many2one(
        'midvex.conversation.identity', ondelete='restrict', index=True,
        help='Who the business is talking to, at the channel level.')
    partner_id = fields.Many2one(
        'res.partner', related='identity_id.partner_id', store=True, index=True,
        help='Derived from the identity, so linking a contact reaches every thread it '
             'has rather than one.')
    assigned_user_id = fields.Many2one(
        'res.users', string='Assigned To', index=True, ondelete='set null')
    status = fields.Selection(STATUSES, default='new', required=True, index=True)
    priority = fields.Selection(
        [('0', 'Normal'), ('1', 'High'), ('2', 'Urgent')], default='0')
    language_code = fields.Char(
        help="The language this customer writes in, as first detected. Used to pick a "
             'provider template; never overwrites what they actually said.')
    first_channel_code = fields.Char(readonly=True)
    last_channel_code = fields.Char(readonly=True)
    first_response_at = fields.Datetime(
        readonly=True,
        help='When an agent first replied. The number a supervisor actually cares '
             'about, and impossible to reconstruct later, so it is stamped once.')
    last_message_at = fields.Datetime(readonly=True, index=True)
    resolved_at = fields.Datetime(readonly=True)
    session_ids = fields.One2many('midvex.conversation.session', 'thread_id')
    message_ids = fields.One2many('midvex.conversation.message', 'thread_id')
    assignment_event_ids = fields.One2many(
        'midvex.conversation.assignment.event', 'thread_id')
    message_count = fields.Integer(compute='_compute_counts')
    unanswered = fields.Boolean(
        compute='_compute_unanswered', store=True,
        help='The customer spoke last. What an agent filters their inbox by, so it is '
             'stored rather than computed on the fly.')
    active = fields.Boolean(default=True)

    @api.depends('message_ids')
    def _compute_counts(self):
        for thread in self:
            thread.message_count = len(thread.message_ids)

    @api.depends('message_ids.direction', 'message_ids.create_date')
    def _compute_unanswered(self):
        for thread in self:
            # Internal notes and system entries do not count as an answer — a
            # colleague reading the thread is not the customer hearing back.
            conversational = thread.message_ids.filtered(
                lambda message: message.direction in ('inbound', 'outbound'))
            last = conversational.sorted('id')[-1:]
            thread.unanswered = bool(last) and last.direction == 'inbound'

    @api.constrains('company_id', 'identity_id')
    def _check_identity_company(self):
        """The same number contacting two companies is two relationships.

        Without this an identity created for one company could be threaded
        under another, which is the quiet start of a cross-company leak: every
        message on that thread would then be readable by the wrong people.
        """
        for thread in self:
            identity = thread.identity_id
            if identity and identity.sudo().company_id != thread.company_id:
                raise ValidationError(_(
                    'This conversation belongs to %(thread)s but the identity belongs '
                    'to %(identity)s. A conversation cannot span companies.',
                    thread=thread.company_id.display_name,
                    identity=identity.sudo().company_id.display_name))

    # --- lifecycle -----------------------------------------------------

    def action_assign(self, user, actor=None, reason=None):
        """Give the thread to somebody, and record that it happened.

        Assignment is audited rather than merely written because "who was
        supposed to answer this" is the first question asked about a
        conversation nobody answered, and a bare field write cannot say.
        """
        self.ensure_one()
        if user and user.company_ids and self.company_id not in user.company_ids:
            raise UserError(_(
                'Cannot assign a %(company)s conversation to a user who does not work '
                'for that company.', company=self.company_id.display_name))

        previous = self.assigned_user_id
        if previous == user:
            return False

        self.env['midvex.conversation.assignment.event'].sudo().create({
            'thread_id': self.id,
            'from_user_id': previous.id or False,
            'to_user_id': user.id if user else False,
            'actor_user_id': (actor or self.env.user).id,
            'reason': reason,
        })
        values = {'assigned_user_id': user.id if user else False}
        # Taking an untouched conversation is what opens it. Left in `new` it
        # would keep showing up in the unassigned queue somebody just claimed
        # it from.
        if user and self.status == 'new':
            values['status'] = 'open'
        self.write(values)
        return True

    def action_resolve(self):
        for thread in self:
            thread.write({'status': 'resolved', 'resolved_at': fields.Datetime.now()})
        return True

    def action_reopen(self):
        """Back to waiting on an agent, and the resolution time cleared.

        Cleared rather than kept because it is no longer true: a thread that
        reopens was not resolved then, and leaving the stamp would quietly
        overstate how fast things get closed.
        """
        for thread in self:
            thread.write({'status': 'waiting_agent', 'resolved_at': False})
        return True

    def action_archive_thread(self):
        for thread in self:
            thread.write({'status': 'archived', 'active': False})
        return True

    def _touch(self, channel_code=None, direction=None, when=None):
        """Record that something happened on this thread.

        Called by the service on every message rather than by the message's
        own create(), so that the ordering — reopen before append — stays in
        one readable place instead of inside an ORM hook.
        """
        self.ensure_one()
        when = when or fields.Datetime.now()
        values = {'last_message_at': when}
        if channel_code:
            values['last_channel_code'] = channel_code
            if not self.first_channel_code:
                values['first_channel_code'] = channel_code
        if direction == 'inbound':
            if self.status in ('resolved', 'archived'):
                # A customer replying to something we considered finished
                # reopens it. Appending silently would put their message
                # somewhere nobody is looking.
                values['status'] = 'waiting_agent'
                values['resolved_at'] = False
                values['active'] = True
            elif self.status == 'new' and not self.assigned_user_id:
                # Nobody has claimed it. Leave it in the unassigned queue,
                # which is where somebody will find it — moving it to
                # waiting_agent would imply an agent who does not exist.
                pass
            else:
                # Everything else live. The customer has spoken, so the ball is
                # with us — including on a thread already `open`, which is the
                # ordinary case of an ongoing exchange and the one this missed
                # at first: it read only `new` and `waiting_customer`, so a
                # reply mid-conversation left the status saying nothing was
                # owed.
                values['status'] = 'waiting_agent'
        elif direction == 'outbound':
            values['status'] = 'waiting_customer'
            if not self.first_response_at:
                values['first_response_at'] = when
        self.write(values)
        return True
