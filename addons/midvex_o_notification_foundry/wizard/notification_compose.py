import uuid

from odoo import _, api, fields, models
from odoo.exceptions import UserError


class NotificationCompose(models.TransientModel):
    """Send a message by hand, outside any rule.

    The Message Queue used to look like it could do this — it offered a Create
    button — but a row made there could never be saved: body and
    idempotency_key are required and not editable on that form, and the channel
    was a free text box, which is how the live queue ended up with rows coded
    '1'. The queue is a delivery log, so composing moved here instead.
    """

    _name = 'midvex.notification.compose'
    _description = 'Send a Notification'

    account_id = fields.Many2one(
        'midvex.notification.account', string='Send From', required=True,
        domain="[('state', '=', 'connected'), ('active', '=', True)]",
        default=lambda self: self._default_account())
    channel_code = fields.Selection(related='account_id.channel_code')
    recipient_ids = fields.Many2many(
        'midvex.notification.recipient', string='Send To', required=True,
        domain="[('account_id', '=', account_id), ('state', '=', 'linked')]")
    body = fields.Text(required=True)

    # Set from context when opened from a record's Actions menu, so the send
    # can be written back to that record's chatter.
    res_model = fields.Char(readonly=True)
    res_id = fields.Integer(readonly=True)
    record_name = fields.Char(readonly=True)

    @api.model
    def _default_account(self):
        return self.env['midvex.notification.account'].search(
            [('state', '=', 'connected'), ('active', '=', True)], limit=1)

    @api.onchange('account_id')
    def _onchange_account_id(self):
        """Recipients belong to one account, so switching accounts must clear
        them — otherwise a chat linked to the old bot is silently carried over
        and the send fails with a chat id the new bot has never seen."""
        self.recipient_ids = [(5, 0, 0)]

    @api.model
    def default_get(self, fields_list):
        values = super().default_get(fields_list)
        context = self.env.context
        res_model = context.get('default_res_model') or context.get('active_model')
        res_id = context.get('default_res_id') or context.get('active_id')
        # active_model is set on every action opened from a list or form,
        # including this wizard's own menu entry, where it would point at the
        # wizard itself and post a chatter note onto a transient record.
        if res_model and res_id and res_model != self._name:
            record = self.env[res_model].browse(res_id).exists()
            if record:
                values.update({
                    'res_model': res_model,
                    'res_id': res_id,
                    'record_name': record.display_name,
                })
        return values

    def action_send(self):
        self.ensure_one()
        if not self.recipient_ids:
            raise UserError(_('Choose at least one recipient.'))

        Message = self.env['midvex.notification.message']
        messages = Message
        for recipient in self.recipient_ids:
            messages |= Message.create({
                'name': _('Manual message'),
                # No rule: this did not come from one, and pretending otherwise
                # would put it in the delivery statistics of a rule nobody ran.
                'recipient_id': recipient.id,
                'account_id': self.account_id.id,
                'res_model': self.res_model or False,
                'res_id': self.res_id or False,
                'body': self.body,
                # Nothing to deduplicate against: a person pressing Send twice
                # means it twice, unlike an event that may be replayed.
                'idempotency_key': 'manual-%s' % uuid.uuid4().hex,
            })

        # Sent immediately rather than queued: quiet hours are a cron concern,
        # and someone pressing Send has decided this is worth the interruption.
        # Same reasoning as action_retry().
        messages.action_process()
        self._log_to_chatter(messages)

        sent = len(messages.filtered(lambda item: item.state == 'sent'))
        if sent == len(messages):
            message = _('Sent to %s recipient(s).', len(messages))
            kind = 'success'
        else:
            message = _('%(sent)s of %(total)s sent. See the Message Queue for the rest.',
                        sent=sent, total=len(messages))
            kind = 'warning'
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {'type': kind, 'title': _('Notification'), 'message': message,
                        'next': {'type': 'ir.actions.act_window_close'}},
        }

    def _log_to_chatter(self, messages):
        """Record the send on the originating document.

        Without this a message sent from a lead leaves no trace on the lead,
        and the next person to open it has no idea the customer's team was
        already contacted.
        """
        self.ensure_one()
        if not self.res_model or not self.res_id:
            return
        record = self.env[self.res_model].browse(self.res_id).exists()
        # Not every model has a chatter, and the Actions menu can be bound to
        # one that does not.
        if not record or not hasattr(record, 'message_post'):
            return
        delivered = messages.filtered(lambda item: item.state == 'sent')
        if not delivered:
            return
        names = ', '.join(delivered.mapped('recipient_id.display_name'))
        record.message_post(
            body=_('%(channel)s message sent to %(names)s:',
                    channel=(self.channel_code or '').title() or _('Notification'),
                    names=names) + '<br/>' + (self.body or '').replace('\n', '<br/>'),
            subtype_xmlid='mail.mt_note')
