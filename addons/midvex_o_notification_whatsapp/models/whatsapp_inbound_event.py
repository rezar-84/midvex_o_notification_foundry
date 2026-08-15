from odoo import fields, models


class NotificationInboundEvent(models.Model):
    """A dedupe key for WhatsApp events, on the shared inbound event model.

    The model already has `external_id`, but it cannot carry this: for Telegram
    that column holds the *chat* id, and every message from one chat reuses it.
    A unique constraint over the existing column would reject the second message
    anybody ever sent the bot.

    So WhatsApp gets its own column and its own constraint. Telegram rows leave
    it NULL, and PostgreSQL treats NULLs as distinct under UNIQUE, so any number
    of them coexist — the same reason the recipient model can hold many group
    chats against one account.

    The key is not the wamid alone. One outbound message produces three status
    notifications — sent, delivered, read — all naming the same wamid, so the
    status has to be part of what makes them different. An inbound message keys
    on its wamid alone, which is globally unique.
    """

    _inherit = 'midvex.notification.inbound.event'

    wa_event_key = fields.Char(
        string='WhatsApp Event Key', index=True, readonly=True,
        help='Deterministic identity of one WhatsApp webhook event, used to reject '
             'redeliveries. "msg:<wamid>" for an inbound message, '
             '"status:<wamid>:<state>" for a delivery status.')

    _wa_event_key_uniq = models.Constraint(
        'UNIQUE (account_id, wa_event_key)',
        'This WhatsApp event has already been recorded.')

    def process_conversation_event(self, account, event):
        """Hand a parsed webhook event to whatever threads conversations.

        A no-op here, and deliberately so. Without `midvex_o_conversation_foundry`
        installed there is nowhere for a customer's message to go, and this
        module on its own is still correct: the envelope is stored, deduped and
        acknowledged, delivery statuses update the queue, and free text is read
        by nothing. That is the roadmap's phase-2 exit criterion exactly.

        `midvex_o_conversation_whatsapp` overrides this to build the thread.
        Extending it further — a second bridge, an analytics hook — is ordinary
        model inheritance and needs no change here.
        """
        return False

    @staticmethod
    def build_wa_event_key(event):
        """The dedupe key for one parsed event, or None when it has no identity.

        An event with no key is stored unconditionally rather than dropped.
        Losing a payload we could not identify is worse than keeping a possible
        duplicate of it — the row is evidence, and evidence is what an operator
        needs when a customer says they messaged and nobody answered.
        """
        wamid = event.get('external_message_id')
        if not wamid:
            return None
        if event.get('event_type') == 'status':
            return 'status:%s:%s' % (wamid, event.get('status') or 'unknown')
        return 'msg:%s' % wamid
