from odoo import api, fields, models


class NotificationMessage(models.Model):
    """WhatsApp delivery state on the shared queue row.

    The foundry's own states stop at 'sent' — it is a delivery queue, and once
    a message is out its job is done. WhatsApp keeps talking afterwards:
    delivered, then read, arriving minutes or hours later over the webhook.

    That is genuinely new information and it needs somewhere to live. Adding
    states to the queue would be wrong (the queue has nothing left to do with
    them, and every other channel would grow a state it never reaches), so it
    lives here, on two fields the WhatsApp module adds and only WhatsApp writes.

    Conversation messages will want real delivered_at/read_at timestamps. Those
    belong on midvex.conversation.message in phase 3, not on a queue row.
    """

    _inherit = 'midvex.notification.message'

    wa_message_id = fields.Char(
        string='WhatsApp Message ID', compute='_compute_wa_message_id', store=True, index=True,
        help="Meta's wamid for this message, extracted from the delivery result. Every "
             'status notification names it and nothing else, so it is what links an '
             'inbound status back to the row that produced it.')
    wa_delivery_status = fields.Selection(
        [('sent', 'Sent'), ('delivered', 'Delivered'), ('read', 'Read')],
        string='WhatsApp Delivery', readonly=True, copy=False,
        help='The furthest state WhatsApp has reported. Never moves backwards: statuses '
             'arrive out of order, and `read` routinely lands before `delivered`.')

    @api.depends('result', 'channel_code')
    def _compute_wa_message_id(self):
        """Derived rather than written by the send path.

        Extracting it from the result the adapter already returns keeps the
        foundry's action_process untouched — it knows nothing about wamids and
        should not have to. A stored compute gives the indexed column the
        webhook needs to look a message up in one query.
        """
        for message in self:
            result = message.result if message.channel_code == 'whatsapp' else None
            message.wa_message_id = (result or {}).get('provider_message_id') or False
