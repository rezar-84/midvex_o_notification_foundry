from datetime import timedelta

from odoo import _, api, fields, models
from odoo.exceptions import UserError

#: How long WhatsApp lets a business reply freely after the customer last wrote.
#:
#: Cited from error code 131047 — "More than 24 hours have passed since
#: recipient last replied" — because Meta's overview page names the customer
#: service window without ever stating its duration. See
#: docs/projects/notification_whatsapp/API_RESEARCH.md, checked 2026-08-14.
#:
#: A named constant with that citation beside it, rather than a 24 scattered
#: through the code: this is a provider policy value, and provider policy
#: values change.
CUSTOMER_SERVICE_WINDOW = timedelta(hours=24)


class ConversationSession(models.Model):
    """The WhatsApp messaging window, enforced before an agent types.

    Outside 24 hours from the customer's last message, WhatsApp delivers only
    templates it approved in advance and rejects free text with error 131047.

    Checking at send time would mean the agent writes a reply, sends it, and
    learns from a failed message in the thread that it was never going to
    work. Checking here means the refusal arrives with an explanation and
    before the effort.
    """

    _inherit = 'midvex.conversation.session'

    whatsapp_window_open = fields.Boolean(
        compute='_compute_whatsapp_window',
        help='Whether a free-form reply is currently deliverable on this session.')
    whatsapp_window_closes_at = fields.Datetime(
        compute='_compute_whatsapp_window',
        help='When the 24-hour customer service window shuts. Empty on channels that '
             'have no such window, and on a session the customer has never written to.')

    @api.depends('channel_code', 'message_ids.direction', 'message_ids.create_date')
    def _compute_whatsapp_window(self):
        for session in self:
            if session.channel_code != 'whatsapp':
                # Every other channel is always open as far as this module is
                # concerned. Telegram in particular has no window at all, which
                # is worth remembering before treating WhatsApp's constraints
                # as universal.
                session.whatsapp_window_open = True
                session.whatsapp_window_closes_at = False
                continue

            last_inbound = session._whatsapp_last_inbound_at()
            if not last_inbound:
                # The customer has never written on this session, so no window
                # was ever opened. A business-initiated conversation needs an
                # approved template regardless.
                session.whatsapp_window_open = False
                session.whatsapp_window_closes_at = False
                continue

            closes_at = last_inbound + CUSTOMER_SERVICE_WINDOW
            session.whatsapp_window_closes_at = closes_at
            session.whatsapp_window_open = closes_at > fields.Datetime.now()

    def _whatsapp_last_inbound_at(self):
        """When the customer last wrote on this session.

        Read from the messages rather than from `last_activity_at`, which moves
        on outbound too — replying to somebody would otherwise keep extending
        the window they opened, which is exactly backwards.
        """
        self.ensure_one()
        last = self.env['midvex.conversation.message'].sudo().search(
            [('session_id', '=', self.id), ('direction', '=', 'inbound')],
            order='id desc', limit=1)
        return last.create_date if last else False

    def check_outbound_allowed(self, message_type='text'):
        result = super().check_outbound_allowed(message_type)
        if self.channel_code != 'whatsapp':
            return result

        # A template is the thing that *is* allowed outside the window, so it
        # is never what the window refuses.
        if message_type == 'template':
            return result

        if not self.whatsapp_window_open:
            closed_at = self.whatsapp_window_closes_at
            if closed_at:
                raise UserError(_(
                    "WhatsApp's 24-hour customer service window for this conversation "
                    'closed at %(closed)s. Only a pre-approved template can be '
                    'delivered now — a free-form reply would be rejected by the '
                    'provider.', closed=closed_at))
            raise UserError(_(
                'This customer has not written on WhatsApp yet, so there is no open '
                'messaging window. A business-initiated message must be a pre-approved '
                'template.'))
        return result
