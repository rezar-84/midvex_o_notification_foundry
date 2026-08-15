from odoo import fields, models


class ConversationAssignmentEvent(models.Model):
    """Who handed this conversation to whom, when, and why.

    Exists because "who was supposed to answer this" is the first question
    asked about a conversation nobody answered, and `assigned_user_id` can only
    say who holds it now. A reassignment away from someone who was busy and a
    reassignment away from someone who was on holiday look identical in the
    field and different here.

    Append-only by construction: nothing writes these after create, and the
    ACLs below grant no write or unlink to anybody.
    """

    _name = 'midvex.conversation.assignment.event'
    _description = 'Conversation Assignment Event'
    _order = 'id desc'

    thread_id = fields.Many2one(
        'midvex.conversation.thread', required=True, ondelete='cascade', index=True)
    company_id = fields.Many2one(related='thread_id.company_id', store=True, index=True)
    from_user_id = fields.Many2one('res.users', string='From', ondelete='set null')
    to_user_id = fields.Many2one('res.users', string='To', ondelete='set null')
    actor_user_id = fields.Many2one(
        'res.users', string='Changed By', ondelete='set null',
        help='Who made the change, which is often neither of the two above — a '
             'supervisor reassigning someone else\'s work.')
    reason = fields.Char()
