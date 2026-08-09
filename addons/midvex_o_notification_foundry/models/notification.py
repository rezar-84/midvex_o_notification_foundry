import uuid
from datetime import datetime, time, timedelta

import pytz

from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError, ValidationError


def _tz_get(self):
    return [(name, name) for name in pytz.all_timezones]


class NotificationChannel(models.Model):
    _name = 'midvex.notification.channel'
    _description = 'Notification Channel'
    _rec_name = 'name'

    name = fields.Char(required=True, translate=True)
    # Selection, not Char: the only workable values are the codes adapters
    # register themselves under, and free text let a channel be created with a
    # code no adapter answers to. The dispatcher copies the code onto every
    # message, so the mistake surfaced far away, at send time, as "No
    # notification adapter is installed for channel X".
    code = fields.Selection(selection='_selection_code', required=True, index=True)
    active = fields.Boolean(default=True)
    module_name = fields.Char()
    documentation_url = fields.Char()
    supports_inbound = fields.Boolean(default=False)
    _channel_code_uniq = models.Constraint('UNIQUE (code)', 'Channel code must be unique.')

    @api.model
    def _selection_code(self):
        """Offer exactly the adapters this database has installed.

        A stored code whose adapter module was later uninstalled is kept in the
        list so the record still displays it rather than showing an empty field
        and losing the value on the next save.
        """
        from ..services.registry import available_adapter_codes
        codes = list(available_adapter_codes())
        stored = self.env['midvex.notification.channel'].sudo().search([]).mapped('code')
        for code in stored:
            if code and code not in codes:
                codes.append(code)
        return [(code, code) for code in sorted(codes)]


class NotificationAccount(models.Model):
    _name = 'midvex.notification.account'
    _description = 'Notification Account'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _check_company_auto = True

    name = fields.Char(required=True, tracking=True)
    channel_id = fields.Many2one('midvex.notification.channel', required=True, ondelete='restrict')
    # Selection, not Char: a related field must match the type of what it
    # mirrors, and channel.code became a Selection so it can only offer codes
    # an adapter actually answers to.
    channel_code = fields.Selection(related='channel_id.code', store=True, index=True)
    company_id = fields.Many2one('res.company', required=True, default=lambda self: self.env.company, index=True)
    active = fields.Boolean(default=True)
    state = fields.Selection([('draft', 'Draft'), ('connected', 'Connected'), ('error', 'Error')],
                              default='draft', required=True, tracking=True)
    api_key = fields.Char(string='Bot Token / API Key', groups='midvex_o_notification_foundry.group_notification_admin')
    api_secret = fields.Char(string='API Secret', groups='midvex_o_notification_foundry.group_notification_admin')
    # Channel-specific but lives here because the account is what an adapter is
    # handed. Blank means plain text, which is what every message sent before
    # this field existed was — so leaving it unset changes nothing.
    parse_mode = fields.Selection(
        [('HTML', 'HTML'), ('MarkdownV2', 'MarkdownV2')],
        string='Message Formatting',
        help="Formatting applied to outgoing messages; leave empty for plain text. "
             "Once set, every message must be valid markup - a lead named "
             "'Smith & Co' is rejected by Telegram unless the template escapes it.",
    )
    webhook_url = fields.Char()
    webhook_secret = fields.Char(groups='midvex_o_notification_foundry.group_notification_admin')
    last_test_at = fields.Datetime(readonly=True)
    last_error = fields.Text(readonly=True)
    recipient_ids = fields.One2many('midvex.notification.recipient', 'account_id')
    notification_message_ids = fields.One2many('midvex.notification.message', 'account_id')
    recipient_count = fields.Integer(compute='_compute_counts')
    message_count = fields.Integer(compute='_compute_counts')

    @api.depends('recipient_ids', 'notification_message_ids.state')
    def _compute_counts(self):
        for account in self:
            account.recipient_count = len(account.recipient_ids)
            account.message_count = len(account.notification_message_ids)

    def _require_manager(self):
        if not self.env.user.has_group('midvex_o_notification_foundry.group_notification_manager'):
            raise AccessError(_('Notification Manager permission is required.'))

    def action_test_connection(self):
        self._require_manager()
        from ..services.registry import get_adapter
        identities = []
        for account in self:
            adapter = get_adapter(account.channel_code)
            try:
                info = adapter.test_connection(account)
            except Exception as error:
                account.write({'state': 'error', 'last_error': str(error)})
                raise
            account.write({'state': 'connected', 'last_test_at': fields.Datetime.now(), 'last_error': False})
            if isinstance(info, dict):
                identity = info.get('username') or info.get('name')
                if identity:
                    identities.append(identity)

        # Success used to be entirely silent — it returned True, so the only
        # signal was the statusbar quietly moving to Connected, and people
        # reasonably read "nothing happened" as "it did not work". Failure was
        # always loud, because the exception above propagates.
        if identities:
            message = _('Connected as %s', ', '.join('@%s' % name for name in identities))
        else:
            message = _('The channel accepted these credentials.')
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'type': 'success',
                'title': _('Connection successful'),
                'message': message,
                'next': {'type': 'ir.actions.act_window_close'},
            },
        }

    def action_register_webhook(self):
        self._require_manager()
        from ..services.registry import get_adapter
        for account in self:
            if not account.webhook_url:
                raise UserError(_('Set a webhook URL before registering it.'))
            adapter = get_adapter(account.channel_code)
            adapter.register_webhook(account, account.webhook_url, account.webhook_secret)
        return True

    def action_view_recipients(self):
        return {'type': 'ir.actions.act_window', 'name': _('Recipients'),
                'res_model': 'midvex.notification.recipient', 'view_mode': 'list,form',
                'domain': [('account_id', '=', self.id)]}

    def action_view_messages(self):
        return {'type': 'ir.actions.act_window', 'name': _('Messages'),
                'res_model': 'midvex.notification.message', 'view_mode': 'list,form',
                'domain': [('account_id', '=', self.id)]}


class NotificationRecipient(models.Model):
    _name = 'midvex.notification.recipient'
    _description = 'Notification Recipient'
    _check_company_auto = True

    # A shared team chat has no owner, so it cannot honestly be modelled as one
    # person's link. Giving it a user_id would also make the dispatcher treat
    # it as that person's private destination and deliver their alerts to the
    # whole room, so the two kinds are kept strictly apart by
    # _check_kind_target below.
    kind = fields.Selection([('user', 'User'), ('group', 'Group Chat')],
                             default='user', required=True, index=True)
    name = fields.Char(string='Chat Name',
                        help='Label for a shared chat. Filled in from the chat title on '
                             'linking if left empty.')
    user_id = fields.Many2one('res.users', ondelete='cascade', index=True)
    account_id = fields.Many2one('midvex.notification.account', required=True, ondelete='cascade', index=True)
    channel_code = fields.Selection(related='account_id.channel_code', store=True, index=True)
    company_id = fields.Many2one(related='account_id.company_id', store=True, index=True)
    external_id = fields.Char(groups='midvex_o_notification_foundry.group_notification_manager')
    external_username = fields.Char(groups='midvex_o_notification_foundry.group_notification_manager')
    state = fields.Selection([('pending', 'Pending'), ('linked', 'Linked'), ('revoked', 'Revoked')],
                              default='pending', required=True)
    # Distinct from `active` and from state='revoked': muting is a temporary,
    # self-service pause that keeps the link intact, so the recipient does not
    # have to go through the link-code flow again to come back.
    muted = fields.Boolean(default=False,
                            help='Delivery is skipped while muted. The link itself is kept.')
    # Quiet hours hold delivery rather than dropping it: an alert that arrives
    # late is still useful, and one silently discarded overnight is the kind of
    # loss nobody notices until it matters.
    quiet_enabled = fields.Boolean(string='Quiet Hours', default=False)
    quiet_start = fields.Float(string='From', default=22.0)
    quiet_end = fields.Float(string='Until', default=7.0)
    tz = fields.Selection(_tz_get, string='Timezone',
                           help='Timezone the quiet hours are read in. Defaults to the '
                                "user's own timezone; a shared chat has no user, so set "
                                'it here.')
    link_code = fields.Char(readonly=True, copy=False)
    link_code_expires_at = fields.Datetime(readonly=True)
    linked_at = fields.Datetime(readonly=True)
    active = fields.Boolean(default=True)
    # Still one link per user per account. Group chats leave user_id NULL, and
    # Postgres treats NULLs as distinct, so any number of them coexist here —
    # which is what we want: one account can serve several team chats.
    _account_recipient_uniq = models.Constraint('UNIQUE (account_id, user_id)',
                                                  'A user already has a recipient link for this account.')

    @api.constrains('kind', 'user_id')
    def _check_kind_target(self):
        for recipient in self:
            if recipient.kind == 'user' and not recipient.user_id:
                raise ValidationError(_('A user recipient needs a user.'))
            if recipient.kind == 'group' and recipient.user_id:
                raise ValidationError(_(
                    'A group chat must not be attached to a user. The dispatcher looks '
                    'recipients up by user, so a group chat carrying one would receive '
                    'that person\'s private alerts.'))

    @api.depends('kind', 'name', 'user_id.name')
    def _compute_display_name(self):
        for recipient in self:
            if recipient.kind == 'group':
                recipient.display_name = recipient.name or _('Unnamed chat')
            else:
                recipient.display_name = recipient.user_id.name or _('Recipient')

    def _check_self_or_manager(self):
        # A group chat has no user_id, so this never matches env.user and
        # managing one always requires the manager group. That is deliberate:
        # a shared chat is not anybody's to mute or unlink from the backend.
        if self.user_id != self.env.user and not self.env.user.has_group(
                'midvex_o_notification_foundry.group_notification_manager'):
            raise AccessError(_('You can only manage your own notification link.'))

    def action_generate_link_code(self):
        for recipient in self:
            recipient._check_self_or_manager()
            recipient.write({
                'link_code': uuid.uuid4().hex[:8].upper(),
                'link_code_expires_at': fields.Datetime.now() + timedelta(minutes=15),
                'state': 'pending',
            })
        return True

    @api.model
    def get_or_create_link(self, user, channel_code):
        account = self.env['midvex.notification.account'].search([
            ('channel_code', '=', channel_code), ('company_id', '=', user.company_id.id),
            ('active', '=', True), ('state', '=', 'connected')], limit=1)
        if not account:
            raise UserError(_('No connected %s account is configured for your company.') % channel_code)
        recipient = self.search([('user_id', '=', user.id), ('account_id', '=', account.id)], limit=1)
        if not recipient:
            recipient = self.create({'user_id': user.id, 'account_id': account.id})
        recipient.action_generate_link_code()
        return recipient

    @api.model
    def find_pending_by_code(self, code):
        """The recipient a live link code belongs to, without redeeming it.

        Split out from process_link_code so a caller can tell *why* a code was
        refused — an expired code and a code sent from the wrong kind of chat
        need different advice, and one boolean cannot carry both.
        """
        if not code:
            return self.browse()
        return self.sudo().search([
            ('link_code', '=', code), ('state', '=', 'pending'),
            ('link_code_expires_at', '>=', fields.Datetime.now())], limit=1)

    @api.model
    def process_link_code(self, code, external_id, external_username=None, chat_title=None):
        if not external_id:
            return False
        recipient = self.find_pending_by_code(code)
        if not recipient:
            return False
        values = {
            'external_id': external_id,
            'external_username': external_username,
            'state': 'linked',
            'linked_at': fields.Datetime.now(),
            'link_code': False,
        }
        # Telegram gives a title for a group chat but not for a DM. Only used
        # to fill a blank, so an admin's own label is never overwritten.
        if recipient.kind == 'group' and chat_title and not recipient.name:
            values['name'] = chat_title
        recipient.write(values)
        return recipient

    @api.model
    def find_linked(self, account, external_id):
        """The linked recipient behind an inbound chat, if any.

        Scoped to the account as well as the chat id: the same person can be
        linked to two bots, and a command sent to one must not act on the
        other's link.
        """
        if not external_id:
            return self.browse()
        return self.sudo().search([
            ('account_id', '=', account.id),
            ('external_id', '=', external_id),
            ('state', '=', 'linked'),
        ], limit=1)

    def _quiet_timezone(self):
        """Whose clock the quiet hours are read on.

        A person's own timezone is the honest default. A group chat has no
        user, so it falls back to the company's and finally to UTC — never to
        the server's local time, which is nobody's working day.
        """
        self.ensure_one()
        return pytz.timezone(
            self.tz or self.user_id.tz or self.company_id.partner_id.tz or 'UTC')

    def _quiet_release_at(self, now=None):
        """When quiet hours end for this recipient, or False if not quiet now.

        Windows wrap midnight — 22:00 to 07:00 is the normal case, not the
        edge case — so "inside the window" cannot be a simple start <= t < end.
        """
        self.ensure_one()
        if not self.quiet_enabled:
            return False
        # A zero-length window is off, not permanently quiet. Without this a
        # recipient who enabled quiet hours and left both bounds equal would
        # never receive anything again.
        if self.quiet_start == self.quiet_end:
            return False

        tz = self._quiet_timezone()
        now = now or fields.Datetime.now()
        local = pytz.utc.localize(now).astimezone(tz)
        minutes = local.hour * 60 + local.minute
        start = int(round(self.quiet_start * 60))
        end = int(round(self.quiet_end * 60))
        if start < end:
            quiet_now = start <= minutes < end
        else:
            quiet_now = minutes >= start or minutes < end
        if not quiet_now:
            return False

        release = datetime.combine(local.date(), time(hour=end // 60, minute=end % 60))
        if release <= local.replace(tzinfo=None):
            release += timedelta(days=1)
        # localize() rather than replace(tzinfo=...): the offset depends on the
        # date, and on a DST boundary the two disagree by an hour.
        return tz.localize(release).astimezone(pytz.utc).replace(tzinfo=None)

    def action_set_muted(self, muted):
        """Pause or resume delivery, keeping the link. Returns whether it changed."""
        self.ensure_one()
        if self.muted == muted:
            return False
        self.sudo().write({'muted': muted})
        return True

    def action_unlink_chat(self):
        """Disconnect a chat at the recipient's own request.

        Revoked rather than deleted so the audit trail and any delivered
        messages keep their target, and the external id is dropped so nothing
        can be sent to a chat that asked to be left alone.
        """
        self.ensure_one()
        self.sudo().write({
            'state': 'revoked',
            'external_id': False,
            'link_code': False,
            'muted': False,
        })
        return True


class NotificationTemplate(models.Model):
    _name = 'midvex.notification.template'
    _description = 'Notification Template'

    name = fields.Char(required=True, translate=True)
    code = fields.Char(required=True, index=True)
    model_id = fields.Many2one('ir.model', required=True, ondelete='cascade')
    model_name = fields.Char(related='model_id.model', string='Technical Model Name', store=True)
    subject = fields.Char(translate=True)
    body = fields.Text(required=True, translate=True,
                        help='Rendered with Odoo inline templating, e.g. {{ object.name }}.')
    active = fields.Boolean(default=True)
    _template_code_uniq = models.Constraint('UNIQUE (code)', 'Template code must be unique.')

    def render(self, record):
        self.ensure_one()
        RenderMixin = self.env['mail.render.mixin']
        body = RenderMixin._render_template(self.body, self.model_name, [record.id],
                                             engine='inline_template')[record.id]
        subject = False
        if self.subject:
            subject = RenderMixin._render_template(self.subject, self.model_name, [record.id],
                                                     engine='inline_template')[record.id]
        return {'subject': subject, 'body': body}


class NotificationRule(models.Model):
    _name = 'midvex.notification.rule'
    _description = 'Notification Rule'
    _check_company_auto = True

    name = fields.Char(required=True)
    model_id = fields.Many2one('ir.model', required=True, ondelete='cascade')
    # Mirrors NotificationTemplate.model_name. Present so the form can offer a
    # real domain builder for trigger_domain instead of a bare text box — the
    # domain widget needs the target model name in a field it can read.
    model_name = fields.Char(related='model_id.model', string='Technical Model Name', store=True)
    trigger = fields.Selection([('on_create', 'On Creation'), ('on_write', 'On Update')],
                                default='on_create', required=True)
    trigger_domain = fields.Char(help='Optional Odoo domain, evaluated against the triggering record. '
                                       'Leave empty to always match.')
    template_id = fields.Many2one('midvex.notification.template', required=True, ondelete='restrict')
    channel_ids = fields.Many2many('midvex.notification.channel', required=True, string='Channels')
    audience_group_ids = fields.Many2many('res.groups', 'notification_rule_group_rel', 'rule_id', 'group_id',
                                           string='Audience Groups')
    audience_user_ids = fields.Many2many('res.users', 'notification_rule_user_rel', 'rule_id', 'user_id',
                                          string='Audience Users')
    # Group chats are addressed directly rather than through res.users: they
    # have no user to resolve, and picking one per rule is the point — a lead
    # alert goes to the sales room, not to every room the bot has joined.
    audience_recipient_ids = fields.Many2many(
        'midvex.notification.recipient', 'notification_rule_recipient_rel', 'rule_id', 'recipient_id',
        string='Audience Chats', domain="[('kind', '=', 'group')]",
        help='Shared chats to notify, in addition to the users above.')
    company_id = fields.Many2one('res.company', required=True, default=lambda self: self.env.company, index=True)
    active = fields.Boolean(default=True)
    automation_id = fields.Many2one('base.automation', string='Automation', readonly=True, copy=False,
                                     help='The automation that makes this rule fire. Maintained '
                                          'automatically; several rules on the same model share one.')

    # --- Wiring -------------------------------------------------------------
    # Nothing calls enqueue_event() by itself. A rule only fires because a
    # base.automation on its model runs a server action that calls it, and
    # until now the single automation that existed was hand-written in the
    # Telegram module's data file. So a rule added through the UI - for another
    # model, or on update - matched nothing and reported no error at all. These
    # methods keep that plumbing in step with the rules that need it.

    _AUTOMATION_CODE = (
        "env['midvex.notification.message'].sudo()._trigger_event(%r, record, %r)")

    def _automation_values(self):
        self.ensure_one()
        return {
            'name': 'Notification: %s on %s' % (
                dict(self._fields['trigger'].selection).get(self.trigger), self.model_name),
            'model_id': self.model_id.id,
            'trigger': self.trigger,
        }

    def _find_or_create_automation(self):
        """One automation per (model, trigger), shared by every rule on it.

        Not one per rule: enqueue_event() already walks every rule matching the
        model and trigger, so a second automation would run the whole set a
        second time. Existing automations are adopted rather than duplicated,
        which matters because a hand-written one is already installed for
        crm.lead on production.
        """
        self.ensure_one()
        Automation = self.env['base.automation'].sudo()
        automation = Automation.search([
            ('model_id', '=', self.model_id.id),
            ('trigger', '=', self.trigger),
        ], limit=1)
        if automation:
            return automation
        automation = Automation.create(self._automation_values())
        event_code = 'created' if self.trigger == 'on_create' else 'updated'
        self.env['ir.actions.server'].sudo().create({
            'name': automation.name,
            'base_automation_id': automation.id,
            'model_id': self.model_id.id,
            'state': 'code',
            'code': self._AUTOMATION_CODE % (self.model_name, event_code),
        })
        return automation

    def _sync_automations(self):
        for rule in self:
            if rule.active:
                automation = rule._find_or_create_automation()
                if rule.automation_id != automation:
                    rule.with_context(skip_automation_sync=True).automation_id = automation
        self._drop_orphan_automations()

    @api.model
    def _drop_orphan_automations(self):
        """Remove automations this model created that no active rule needs.

        Scoped to automations whose server action carries our code, so a
        hand-written or unrelated automation on the same model is never
        deleted out from under someone.
        """
        Automation = self.env['base.automation'].sudo()
        ours = Automation.search([]).filtered(
            lambda item: any('midvex.notification.message' in (action.code or '')
                              for action in item.action_server_ids))
        for automation in ours:
            still_needed = self.sudo().search_count([
                ('active', '=', True),
                ('model_id', '=', automation.model_id.id),
                ('trigger', '=', automation.trigger),
            ])
            if not still_needed:
                automation.unlink()

    @api.model_create_multi
    def create(self, vals_list):
        rules = super().create(vals_list)
        rules._sync_automations()
        return rules

    def write(self, vals):
        result = super().write(vals)
        # Only the fields that decide which automation is needed. Without this
        # guard, writing automation_id from _sync_automations would recurse.
        if not self.env.context.get('skip_automation_sync') and (
                {'model_id', 'trigger', 'active'} & set(vals)):
            self._sync_automations()
        return result

    def unlink(self):
        result = super().unlink()
        self._drop_orphan_automations()
        return result


class NotificationMessage(models.Model):
    _name = 'midvex.notification.message'
    _description = 'Notification Message'
    _order = 'id desc'
    _check_company_auto = True

    name = fields.Char(required=True, default=lambda self: _('Notification'))
    rule_id = fields.Many2one('midvex.notification.rule', ondelete='set null', index=True)
    recipient_id = fields.Many2one('midvex.notification.recipient', required=True, ondelete='cascade', index=True)
    account_id = fields.Many2one('midvex.notification.account', required=True, ondelete='cascade', index=True)
    company_id = fields.Many2one(related='account_id.company_id', store=True, index=True)
    # Was a free-text Char, which rendered as a text box on the form and let a
    # message be created with a channel no adapter answers to — that is how the
    # live queue ended up with rows coded '1', failing at send time with "No
    # notification adapter is installed for channel 1". Derived from the
    # account now, so new messages cannot disagree with the account they are
    # sent through. Rows that already exist are NOT fixed by this: a stored
    # related field is only computed where it is marked for recomputation, and
    # an already-populated column is not — verified on a real upgrade, where a
    # poisoned row survived untouched. They are repaired by
    # migrations/19.0.1.1.0/post-migration.py instead.
    channel_code = fields.Selection(related='account_id.channel_code', store=True, index=True)
    res_model = fields.Char()
    res_id = fields.Integer()
    subject = fields.Char()
    body = fields.Text(required=True)
    state = fields.Selection([('pending', 'Pending'), ('sending', 'Sending'), ('sent', 'Sent'),
                               ('failed', 'Failed'), ('quarantined', 'Quarantined')],
                              default='pending', required=True, index=True)
    idempotency_key = fields.Char(required=True, index=True)
    attempt_count = fields.Integer(default=0, readonly=True)
    max_attempts = fields.Integer(default=3, required=True)
    next_retry_at = fields.Datetime(index=True)
    # Deliberately not next_retry_at: that field means "this failed, try again
    # later" and drives the attempt count and the failure decorations. A held
    # message has not been attempted and nothing is wrong with it.
    hold_until = fields.Datetime(string='Held Until', index=True, readonly=True,
                                  help='Delivery is held until this time, because the '
                                       'recipient is inside their quiet hours.')
    payload = fields.Json()
    result = fields.Json(readonly=True)
    error_code = fields.Char()
    error_message = fields.Text(readonly=True)
    sent_at = fields.Datetime(readonly=True)
    _message_key_uniq = models.Constraint('UNIQUE (idempotency_key)', 'Duplicate notification message.')

    # Adapter delivery results may echo the message body back (e.g. Telegram's sendMessage
    # response includes the sent text). Drop those keys so logs never duplicate recipient
    # message content beyond what troubleshooting needs, per NOTIFICATION_SECURITY.md.
    _METADATA_REDACT_KEYS = ('raw', 'body', 'text')

    def _log(self, status, message_text, error_code=False, metadata=False):
        safe_metadata = {key: value for key, value in (metadata or {}).items()
                          if key not in self._METADATA_REDACT_KEYS}
        self.env['midvex.notification.log'].create({
            'message_id': self.id, 'channel_code': self.channel_code, 'status': status,
            'message': message_text, 'error_code': error_code, 'metadata': safe_metadata,
        })

    def action_process(self):
        from ..services.registry import get_adapter
        for message in self.filtered(lambda item: item.state == 'pending'):
            message.write({'state': 'sending', 'attempt_count': message.attempt_count + 1})
            try:
                adapter = get_adapter(message.channel_code)
                message_dto = {
                    'message_id': message.id,
                    'recipient_external_id': message.recipient_id.external_id,
                    'subject': message.subject,
                    'body': message.body,
                    'template_code': message.rule_id.template_id.code if message.rule_id else False,
                    'res_model': message.res_model,
                    'res_id': message.res_id,
                    'variables': {},
                }
                result = adapter.send(message.account_id, message_dto)
                message.write({'state': 'sent', 'result': result or {}, 'sent_at': fields.Datetime.now()})
                message._log('success', _('Delivered.'), metadata=result)
            except ValidationError as error:
                message.write({'state': 'quarantined', 'error_message': str(error)})
                message._log('warning', str(error), 'QUARANTINED')
            except Exception as error:
                if message.attempt_count < message.max_attempts:
                    message.write({
                        'state': 'pending', 'error_message': str(error),
                        'next_retry_at': fields.Datetime.now() + timedelta(minutes=5),
                    })
                    message._log('warning', str(error), 'RETRY_SCHEDULED')
                else:
                    message.write({'state': 'failed', 'error_message': str(error)})
                    message._log('failed', _('Delivery failed: %s') % str(error), 'DELIVERY_ERROR')
        return True

    def action_retry(self):
        """Put a failed or quarantined message back in the queue and send it now.

        action_process() only looks at state == 'pending', so without this a
        message that failed its attempts could not be retried from the UI at
        all — an admin had to go to the shell. Typical use is after fixing the
        cause outside Odoo (a revoked bot token, a recipient who blocked the
        bot), where the message itself was always fine.

        attempt_count is deliberately not reset: it is the record of what has
        already been tried, and zeroing it would let a permanently broken
        message loop against max_attempts on every retry.
        """
        retryable = self.filtered(lambda item: item.state in ('failed', 'quarantined'))
        # hold_until goes too: retrying by hand is an explicit "send this now",
        # and leaving a hold on would make the button appear to do nothing.
        retryable.write({'state': 'pending', 'next_retry_at': False, 'hold_until': False})
        return retryable.action_process()

    @api.model
    def cron_process_pending(self):
        """Send what is due, and hold back what the recipient is asleep for.

        Quiet hours are enforced here rather than in action_process() so that
        pressing Send or Retry in the backend still goes out immediately: an
        admin acting by hand has decided the message is worth the interruption.
        """
        now = fields.Datetime.now()
        messages = self.search([
            ('state', '=', 'pending'),
            '|', ('next_retry_at', '=', False), ('next_retry_at', '<=', now),
            '|', ('hold_until', '=', False), ('hold_until', '<=', now),
        ], limit=50)
        ready = self.browse()
        for message in messages:
            release = message.recipient_id._quiet_release_at(now)
            if not release:
                # Clears a stale hold whose window has since passed or been
                # turned off, so the field always reads as the current plan.
                if message.hold_until:
                    message.hold_until = False
                ready |= message
                continue
            # Logged only when the hold is new. The cron runs every few
            # minutes, and re-logging each pass would bury the real delivery
            # history under one line per message per tick.
            if not message.hold_until:
                message._log('warning', _('Held until %s: the recipient is in quiet hours.')
                              % release, 'QUIET_HOURS')
            message.hold_until = release
        return ready.action_process()

    @api.model
    def _trigger_event(self, model_name, record, event_code):
        from ..services.dispatcher import enqueue_event
        return enqueue_event(self.env, model_name, record, event_code)


class NotificationLog(models.Model):
    _name = 'midvex.notification.log'
    _description = 'Notification Delivery Log'
    _order = 'create_date desc, id desc'
    _check_company_auto = True

    message_id = fields.Many2one('midvex.notification.message', string='Notification', ondelete='cascade', index=True)
    company_id = fields.Many2one(related='message_id.company_id', store=True, index=True)
    channel_code = fields.Char()
    status = fields.Selection([('success', 'Success'), ('warning', 'Warning'), ('failed', 'Failed')], required=True)
    message = fields.Text(required=True)
    error_code = fields.Char()
    metadata = fields.Json()


class NotificationInboundEvent(models.Model):
    _name = 'midvex.notification.inbound.event'
    _description = 'Notification Inbound Event'
    _order = 'create_date desc, id desc'
    _check_company_auto = True

    channel_id = fields.Many2one('midvex.notification.channel', required=True, ondelete='cascade')
    account_id = fields.Many2one('midvex.notification.account', required=True, ondelete='cascade')
    company_id = fields.Many2one(related='account_id.company_id', store=True, index=True)
    event_type = fields.Char()
    external_id = fields.Char()
    raw_payload = fields.Json(groups='midvex_o_notification_foundry.group_notification_admin')
    processed = fields.Boolean(default=False)
    processed_at = fields.Datetime()
    recipient_id = fields.Many2one('midvex.notification.recipient', ondelete='set null')
    error_message = fields.Text()
