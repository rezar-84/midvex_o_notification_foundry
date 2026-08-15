from odoo import fields, models


class NotificationMessage(models.Model):
    """Report a delivery job's outcome back to the conversation it belongs to.

    The dependency runs one way on purpose. `midvex_o_notification_foundry`
    knows nothing about conversations and must not — it is a queue, and a queue
    that knew what its rows meant would be the two foundries bleeding into each
    other. So the *conversation* module reaches down and reads the outcome,
    rather than the queue reaching up to announce it.

    Implemented by extending the queue's own model here rather than by polling
    it: the conversation message has to reflect a send within the same
    transaction that made it, or an agent watching the thread sees their reply
    sit at "submitted" until something else happens to touch it.
    """

    _inherit = 'midvex.notification.message'

    conversation_message_ids = fields.One2many(
        'midvex.conversation.message', 'delivery_id', string='Conversation Messages')

    def action_process(self):
        result = super().action_process()
        self._sync_conversation_messages()
        return result

    def _handle_failure(self, error):
        result = super()._handle_failure(error)
        self._sync_conversation_messages()
        return result

    def _sync_conversation_messages(self):
        """Mirror this job's outcome onto the durable message.

        Only the outcomes that mean something to a person reading the thread.
        A job that is pending a retry is not shown as failed — it has not
        failed, and telling an agent it did would have them apologise for a
        message that is about to arrive.
        """
        for delivery in self:
            messages = delivery.conversation_message_ids
            if not messages:
                continue

            if delivery.state == 'sent':
                provider_message_id = (delivery.result or {}).get('provider_message_id')
                for message in messages:
                    if provider_message_id and not message.provider_message_id:
                        message.write({'provider_message_id': str(provider_message_id)})
                    message._apply_delivery_state('sent')

            elif delivery.state in ('failed', 'quarantined'):
                for message in messages:
                    message._apply_failure(
                        error_code=delivery.error_code,
                        # The queue already keeps this free of credentials and
                        # headers; it is the adapter's safe_error_message.
                        safe_message=delivery.error_message,
                        when=fields.Datetime.now())
