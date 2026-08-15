import logging
from datetime import datetime, timezone

from odoo import fields, models

from odoo.addons.midvex_o_conversation_foundry.services import conversation

_logger = logging.getLogger(__name__)

#: Provider status → the conversation foundry's delivery ladder. `failed` is
#: handled separately because it is terminal rather than a rung.
_STATUS_MAP = {
    'sent': 'sent',
    'delivered': 'delivered',
    'read': 'read',
}


class NotificationInboundEvent(models.Model):
    """Turn a parsed WhatsApp webhook event into a conversation.

    This is the whole bridge. The webhook already verified the signature,
    stored the envelope and deduped it; the adapter already normalized the
    payload. What was missing was somebody to take a parsed customer message
    and put it somewhere a person will see it.

    It lives on the shared inbound event model (ADR-019) and overrides the
    no-op hook `midvex_o_notification_whatsapp` calls. Neither of those modules
    changes; installing this one is what makes inbound text stop being a
    stored-and-dropped dead end.
    """

    _inherit = 'midvex.notification.inbound.event'

    def process_conversation_event(self, account, event):
        result = super().process_conversation_event(account, event)

        if event.get('event_type') == 'status':
            return self._whatsapp_apply_conversation_status(account, event) or result
        return self._whatsapp_thread_message(account, event) or result

    # --- inbound messages ----------------------------------------------

    def _whatsapp_thread_message(self, account, event):
        """File a customer's message under a thread they own.

        Company resolution comes from the account, which the webhook matched
        from `value.metadata.phone_number_id`. Never from anything the sender
        controls — an inbound payload carries no `to` field, and the sender's
        own number is the one thing an attacker could choose.
        """
        self.ensure_one()
        sender = event.get('sender_identifier')
        if not sender:
            # A message with no sender is not something we can thread. Recorded
            # as ignored rather than failed: nothing is wrong, there is simply
            # nobody to attribute it to.
            self.write({'processing_state': 'ignored'})
            return False

        adapter = self._whatsapp_adapter()
        normalized = adapter.normalize_identity(sender) if adapter else sender
        if not normalized:
            self.write({'processing_state': 'ignored'})
            return False

        company = account.sudo().company_id
        identity = conversation.ensure_identity(
            self.env, company, 'whatsapp', normalized,
            display_identifier=event.get('external_username') or normalized)
        thread = conversation.ensure_thread(
            self.env, company, identity, channel_code='whatsapp')
        session = conversation.open_session(
            self.env, thread, account, normalized,
            external_session_id=event.get('waba_id'))

        message = conversation.record_inbound(self.env, session, {
            'external_message_id': event.get('external_message_id'),
            'message_type': event.get('message_type') or 'text',
            # An unsupported type has no body. Recorded with its type so an
            # agent sees "the customer sent an image" rather than an empty line
            # — and so phase 11 has something to backfill against.
            'body': event.get('text'),
            'timestamp': self._whatsapp_timestamp(event),
        }, inbound_event=self)
        return message

    @staticmethod
    def _whatsapp_timestamp(event):
        """Meta sends a Unix timestamp as a string.

        Returns None rather than guessing when it is missing or unparseable;
        the service falls back to now, which is close enough and honest.
        """
        raw = event.get('timestamp')
        if not raw:
            return None
        try:
            # Odoo stores naive UTC, so the tzinfo is dropped deliberately
            # after parsing rather than never being applied — the difference
            # matters on a machine whose local time is not UTC.
            moment = datetime.fromtimestamp(int(raw), tz=timezone.utc)
            return fields.Datetime.to_string(moment.replace(tzinfo=None))
        except (TypeError, ValueError, OSError, OverflowError):
            return None

    # --- delivery statuses ----------------------------------------------

    def _whatsapp_apply_conversation_status(self, account, event):
        """Mirror a delivery status onto the conversation message.

        The notification queue already had its own copy updated by the webhook.
        This is the durable half: the queue row stops mattering once sent, and
        the thread is what an agent reads a week later.
        """
        self.ensure_one()
        status = event.get('status')
        mapped = _STATUS_MAP.get(status)
        if status == 'failed':
            errors = event.get('errors') or []
            detail = errors[0] if errors else {}
            return conversation.apply_status(
                self.env, account, event.get('external_message_id'), 'failed',
                error_code=str(detail.get('code') or 'WHATSAPP_DELIVERY_FAILED'),
                safe_message=(detail.get('error_data') or {}).get('details')
                or detail.get('title'))
        if not mapped:
            self.write({'processing_state': 'ignored'})
            return False
        return conversation.apply_status(
            self.env, account, event.get('external_message_id'), mapped,
            when=self._whatsapp_timestamp(event))

    @staticmethod
    def _whatsapp_adapter():
        from odoo.addons.midvex_o_notification_foundry.services.registry import get_adapter
        try:
            return get_adapter('whatsapp')
        except Exception:
            # The module cannot be installed without the adapter, so this is
            # defensive rather than expected — but a registry miss must not
            # take down a webhook.
            _logger.warning('WhatsApp adapter is not registered.')
            return None
