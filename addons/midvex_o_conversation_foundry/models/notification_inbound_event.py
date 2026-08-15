from odoo import fields, models


class NotificationInboundEvent(models.Model):
    """What a webhook envelope turned into, once something processed it.

    ADR-019: one envelope store, shared. The webhook is already shared — Meta
    delivers a number's callbacks to exactly one URL — so the controller writes
    customer messages and delivery statuses through the same door, before it
    knows which is which. Splitting the table would mean choosing at the moment
    it knows least, and would split the dedupe key space in two.

    These fields are the conversation half's view of that shared row: where the
    event ended up, and whether it got there.
    """

    _inherit = 'midvex.notification.inbound.event'

    conversation_thread_id = fields.Many2one(
        'midvex.conversation.thread', ondelete='set null', index=True,
        string='Conversation',
        help='The thread this envelope was filed under, once it was processed.')
    conversation_message_id = fields.Many2one(
        'midvex.conversation.message', ondelete='set null', index=True,
        string='Conversation Message',
        help='The durable message this envelope produced. Empty on an event that '
             'produced none — a delivery status, or a type nothing reads yet.')
    processing_state = fields.Selection(
        [('received', 'Received'), ('processing', 'Processing'),
         ('processed', 'Processed'), ('failed', 'Failed'), ('ignored', 'Ignored')],
        default='received', index=True,
        help='Finer than the `processed` flag, which cannot tell "nothing to do with '
             'this" apart from "we have not got to it". Ignored is a resting state; '
             'failed wants somebody.')
    retry_count = fields.Integer(default=0, readonly=True)
    correlation_id = fields.Char(
        index=True, readonly=True,
        help='Ties this envelope to the log lines it produced. The runbook asks people '
             'to search by it, so it has to survive into the logs rather than only '
             'exist here.')
