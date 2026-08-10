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

    def action_open_compose(self):
        """Open the send wizard already addressed to this recipient.

        The quickest honest answer to "is this chat actually working?", which
        previously meant creating a lead and hoping.
        """
        self.ensure_one()
        action = self.env['ir.actions.act_window']._for_xml_id(
            'midvex_o_notification_foundry.action_notification_compose')
        action['context'] = {
            'default_account_id': self.account_id.id,
            'default_recipient_ids': [(6, 0, self.ids)],
        }
        return action

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
    trigger = fields.Selection([('on_create', 'On Creation'), ('on_write', 'On Update'),
                                 ('on_schedule', 'On Schedule')],
                                default='on_create', required=True)
    trigger_domain = fields.Char(help='Optional Odoo domain, evaluated against the triggering record. '
                                       'Leave empty to always match.')
    # --- Schedule (trigger == 'on_schedule' only) ---------------------------
    # A scheduled rule reacts to a date passing rather than to somebody saving
    # a record, which is the only way to express "this invoice is now overdue".
    # These three map straight onto base.automation's on_time fields; see
    # _automation_values.
    date_field_id = fields.Many2one(
        'ir.model.fields', string='Date Field', ondelete='cascade',
        domain="[('model_id', '=', model_id), ('ttype', 'in', ('date', 'datetime'))]",
        help='The date this rule watches. The rule fires once per record, as that '
              'date crosses the offset below.')
    schedule_offset = fields.Integer(
        string='Offset (days)', default=0,
        help='How many days away from the date field to fire. 0 fires on the date itself.')
    schedule_offset_mode = fields.Selection([('after', 'After'), ('before', 'Before')],
                                             string='Offset Direction', default='after')
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
                                          'automatically; several rules on the same model share one, '
                                          'except scheduled rules, which each own theirs.')

    @api.constrains('trigger', 'date_field_id')
    def _check_schedule(self):
        for rule in self:
            if rule.trigger != 'on_schedule':
                continue
            if not rule.date_field_id:
                raise ValidationError(_('A scheduled rule needs a date field to watch.'))
            if rule.date_field_id.model != rule.model_name:
                raise ValidationError(_('%(field)s belongs to %(other)s, not to %(model)s.') % {
                    'field': rule.date_field_id.name,
                    'other': rule.date_field_id.model,
                    'model': rule.model_name,
                })

    # --- Wiring -------------------------------------------------------------
    # Nothing calls enqueue_event() by itself. A rule only fires because a
    # base.automation on its model runs a server action that calls it, and
    # until now the single automation that existed was hand-written in the
    # Telegram module's data file. So a rule added through the UI - for another
    # model, or on update - matched nothing and reported no error at all. These
    # methods keep that plumbing in step with the rules that need it.

    _AUTOMATION_CODE = (
        "env['midvex.notification.message'].sudo()._trigger_event(%r, record, %r)")
    # Scheduled rules name themselves in the call. Their automations are not
    # shared, so without the rule id the automation for "due soon" would also
    # enqueue "overdue" for any record both domains happen to match.
    _SCHEDULED_AUTOMATION_CODE = (
        "env['midvex.notification.message'].sudo()._trigger_event(%r, record, %r, rule_id=%d)")

    _EVENT_CODES = {'on_create': 'created', 'on_write': 'updated', 'on_schedule': 'scheduled'}

    def _automation_values(self):
        self.ensure_one()
        values = {
            'name': 'Notification: %s on %s' % (
                dict(self._fields['trigger'].selection).get(self.trigger), self.model_name),
            'model_id': self.model_id.id,
            'trigger': self.trigger,
        }
        if self.trigger != 'on_schedule':
            return values
        # base.automation calls the time-based trigger 'on_time', and drives it
        # from its own cron. Its @api.constrains rejects a negative delay, so
        # "before" is expressed through the mode and never through the sign.
        values.update({
            'name': 'Notification: %s (%s)' % (self.name, self.model_name),
            'trigger': 'on_time',
            'trg_date_id': self.date_field_id.id,
            'trg_date_range': abs(self.schedule_offset),
            'trg_date_range_mode': self.schedule_offset_mode,
            'trg_date_range_type': 'day',
            # Given to the automation as well as kept on the rule: this one is
            # applied in the cron's search, so a rule watching invoices does
            # not drag every journal entry through the dispatcher first.
            'filter_domain': self.trigger_domain or False,
        })
        return values

    def _find_or_create_automation(self):
        """One automation per (model, trigger), shared by every rule on it.

        Not one per rule: enqueue_event() already walks every rule matching the
        model and trigger, so a second automation would run the whole set a
        second time. Existing automations are adopted rather than duplicated,
        which matters because a hand-written one is already installed for
        crm.lead on production.

        Scheduled rules are the exception and own theirs outright: the watched
        date field, the offset and the domain all live on the automation, so
        two scheduled rules on one model cannot describe themselves with one.
        """
        self.ensure_one()
        Automation = self.env['base.automation'].sudo()
        if self.trigger == 'on_schedule':
            if self.automation_id:
                # Keep it in step - editing the offset or the domain on the rule
                # has to reach the automation, or the cron keeps the old window.
                self.automation_id.write(self._automation_values())
                return self.automation_id
        else:
            automation = Automation.search([
                ('model_id', '=', self.model_id.id),
                ('trigger', '=', self.trigger),
            ], limit=1)
            if automation:
                return automation
        automation = Automation.create(self._automation_values())
        event_code = self._EVENT_CODES[self.trigger]
        if self.trigger == 'on_schedule':
            # base.automation defaults last_run to the epoch, and its cron fires
            # every record whose date crossed between last_run and now. Left
            # alone, switching this rule on would treat every invoice overdue
            # since 1970 as newly due and enqueue the lot in one go.
            automation.last_run = fields.Datetime.now()
            code = self._SCHEDULED_AUTOMATION_CODE % (self.model_name, event_code, self.id)
        else:
            code = self._AUTOMATION_CODE % (self.model_name, event_code)
        self.env['ir.actions.server'].sudo().create({
            'name': automation.name,
            'base_automation_id': automation.id,
            'model_id': self.model_id.id,
            'state': 'code',
            'code': code,
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
            if automation.trigger == 'on_time':
                # A scheduled automation belongs to exactly one rule, so the
                # headcount below cannot see it: two scheduled rules on one
                # model would keep each other's automations alive forever.
                still_needed = self.sudo().search_count([
                    ('active', '=', True),
                    ('automation_id', '=', automation.id),
                ])
            else:
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
        # Only the fields that decide which automation is needed, or - for a
        # scheduled rule, whose whole window lives on the automation - what it
        # should say. Without this guard, writing automation_id from
        # _sync_automations would recurse.
        if not self.env.context.get('skip_automation_sync') and (
                {'model_id', 'trigger', 'active', 'name', 'date_field_id',
                 'schedule_offset', 'schedule_offset_mode', 'trigger_domain'} & set(vals)):
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
                                  help='Delivery is held until this time, either because the '
                                       'recipient is inside their quiet hours or because the '
                                       "channel's rate limit would be breached.")
    # One field answering "why is this not sending", rather than a second
    # datetime per reason: the two holds behave identically and only differ in
    # what an admin should do about them - wait, or reconsider the audience.
    hold_reason = fields.Selection([('quiet_hours', 'Quiet Hours'),
                                     ('rate_limit', 'Rate Limit')],
                                    readonly=True)
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
                message._handle_failure(error)
        return True

    # 1 minute, 5, then 25. The old behaviour was a flat five minutes, which
    # retried a briefly-unreachable channel too slowly and a genuinely broken
    # one too eagerly.
    _RETRY_BACKOFF_MINUTES = (1, 5, 25)

    def _handle_failure(self, error):
        """Decide what a failed send means, using the adapter's own verdict.

        parse_error and its retryable/retry_after_seconds keys have been in
        ADAPTER_CONTRACT.md from the start, and nothing ever called them: every
        failure got the same flat retry and consumed an attempt. That made
        being rate-limited fatal - three 429s, which say nothing at all about
        the message, marked a perfectly good alert permanently failed.
        """
        self.ensure_one()
        from ..services.registry import get_adapter
        try:
            verdict = get_adapter(self.channel_code).parse_error(error) or {}
        except Exception:
            # An adapter that cannot classify its own failure must not turn a
            # delivery problem into a traceback in the cron.
            verdict = {}

        text = verdict.get('message') or str(error)
        error_code = verdict.get('error_code') or 'DELIVERY_ERROR'
        retry_after = verdict.get('retry_after_seconds')

        if retry_after is not None:
            # Gives back the attempt action_process took on the way in. The
            # channel asked us to wait, which is not a failed attempt, and
            # counting it would let a busy hour destroy messages that were
            # never really tried.
            self.write({
                'state': 'pending', 'error_message': text, 'error_code': error_code,
                'attempt_count': max(0, self.attempt_count - 1),
                'next_retry_at': fields.Datetime.now() + timedelta(seconds=int(retry_after)),
            })
            self._log('warning', text, error_code)
            self._trigger_queue(at=self.next_retry_at)
            return

        if not verdict.get('retryable', True):
            self.write({'state': 'quarantined', 'error_message': text, 'error_code': error_code})
            self._log('warning', text, error_code)
            return

        if self.attempt_count < self.max_attempts:
            index = min(self.attempt_count, len(self._RETRY_BACKOFF_MINUTES)) - 1
            delay = self._RETRY_BACKOFF_MINUTES[max(0, index)]
            self.write({
                'state': 'pending', 'error_message': text, 'error_code': error_code,
                'next_retry_at': fields.Datetime.now() + timedelta(minutes=delay),
            })
            self._log('warning', text, 'RETRY_SCHEDULED')
            self._trigger_queue(at=self.next_retry_at)
            return

        self.write({'state': 'failed', 'error_message': text, 'error_code': error_code})
        self._log('failed', _('Delivery failed: %s') % text, error_code)

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

    def _throttle_release_at(self, now=None):
        """When sending this now would breach the channel's rate limits, the
        moment it stops doing so. False when it is free to go.

        Shaped like the recipient's _quiet_release_at() on purpose: both answer
        "not yet, and here is when", and cron_process_pending treats them the
        same way.

        The limits are read off the adapter, which is where the channel's API
        research lives - the foundry knows only that a channel may declare
        them. An adapter that declares none is never throttled, which keeps
        this invisible to channels whose API does not need it.
        """
        self.ensure_one()
        now = now or fields.Datetime.now()
        from ..services.registry import get_adapter
        try:
            adapter = get_adapter(self.channel_code)
        except UserError:
            # No adapter means this message cannot send at all; let
            # action_process report that rather than silently holding it here.
            return False

        releases = []
        Sent = self.sudo()
        chat_seconds = getattr(adapter, 'rate_limit_chat_seconds', 0)
        if chat_seconds:
            last = Sent.search([
                ('recipient_id', '=', self.recipient_id.id),
                ('state', '=', 'sent'), ('sent_at', '!=', False),
            ], order='sent_at desc', limit=1)
            if last and last.sent_at > now - timedelta(seconds=chat_seconds):
                releases.append(last.sent_at + timedelta(seconds=chat_seconds))

        group_per_minute = getattr(adapter, 'rate_limit_group_per_minute', 0)
        if group_per_minute and self.recipient_id.kind == 'group':
            recent = Sent.search([
                ('recipient_id', '=', self.recipient_id.id),
                ('state', '=', 'sent'),
                ('sent_at', '>=', now - timedelta(minutes=1)),
            ], order='sent_at asc')
            if len(recent) >= group_per_minute:
                # The oldest one still inside the window has to age out before
                # there is room for another.
                oldest_blocking = recent[len(recent) - group_per_minute]
                releases.append(oldest_blocking.sent_at + timedelta(minutes=1))

        global_per_second = getattr(adapter, 'rate_limit_global_per_second', 0)
        if global_per_second:
            in_flight = Sent.search_count([
                ('account_id', '=', self.account_id.id),
                ('state', '=', 'sent'),
                ('sent_at', '>=', now - timedelta(seconds=1)),
            ])
            if in_flight >= global_per_second:
                releases.append(now + timedelta(seconds=1))

        # Several limits can apply at once, and the message is only free when
        # the last of them has passed.
        return max(releases) if releases else False

    @api.model
    def _trigger_queue(self, at=None):
        """Wake the queue cron, now or at a given moment.

        This is what makes delivery prompt: the cron's own interval is a
        safety net for retries and releases, not the delivery path. Odoo
        commits an ir.cron.trigger row and notifies the runner post-commit,
        which is the same mechanism core uses for web push.

        Silent when the cron is missing rather than raising: a database
        part-way through an upgrade must not fail to enqueue, and a message
        that is only queued late is a far smaller problem than a save that
        blows up.
        """
        cron = self.env.ref(
            'midvex_o_notification_foundry.ir_cron_notification_process_pending',
            raise_if_not_found=False)
        if cron:
            cron.sudo()._trigger(at=at)

    @api.model
    def _batch_size(self):
        """How many messages one queue run drains.

        Configurable because the right number depends on the channel's rate
        limits and the box: too small and a burst takes several runs to clear,
        too large and one run holds the cron worker for a long time.
        """
        value = self.env['ir.config_parameter'].sudo().get_param(
            'midvex_notification.batch_size', '200')
        try:
            return max(1, int(value))
        except (TypeError, ValueError):
            return 200

    @api.model
    def cron_process_pending(self):
        """Send what is due, and hold back what the recipient is asleep for.

        Quiet hours are enforced here rather than in action_process() so that
        pressing Send or Retry in the backend still goes out immediately: an
        admin acting by hand has decided the message is worth the interruption.
        """
        now = fields.Datetime.now()
        # order='id' overrides the model's own 'id desc', which is right for
        # the list view and wrong for a queue: it drained newest-first. That
        # was invisible while everything in a batch went out regardless, but
        # under a rate limit the newest message wins each run and the oldest
        # alert - the one someone has been waiting on longest - is the one that
        # gets deferred again and again.
        messages = self.search([
            ('state', '=', 'pending'),
            '|', ('next_retry_at', '=', False), ('next_retry_at', '<=', now),
            '|', ('hold_until', '=', False), ('hold_until', '<=', now),
        ], limit=self._batch_size(), order='id')
        holds = []
        for message in messages:
            release = message.recipient_id._quiet_release_at(now)
            if release:
                # Logged only when the hold is new. The cron runs every few
                # minutes, and re-logging each pass would bury the real delivery
                # history under one line per message per tick.
                if not message.hold_until:
                    message._log('warning', _('Held until %s: the recipient is in quiet hours.')
                                  % release, 'QUIET_HOURS')
                message.write({'hold_until': release, 'hold_reason': 'quiet_hours'})
                holds.append(release)
                continue

            # Checked here, one message at a time, and never once for the whole
            # batch: sending each message is what consumes the channel's
            # allowance, so a batch of twenty-five to one group would otherwise
            # all see an empty window and go out together.
            throttle = message._throttle_release_at()
            if throttle:
                if message.hold_reason != 'rate_limit':
                    message._log('warning', _('Held until %s: the channel rate limit '
                                               'would be exceeded.') % throttle, 'RATE_LIMIT')
                message.write({'hold_until': throttle, 'hold_reason': 'rate_limit'})
                holds.append(throttle)
                # Deliberately not a break, and deliberately not a sleep: the
                # rest of the batch is for other chats, and one busy group room
                # must not starve everyone else's alerts - nor hold the only
                # cron worker doing nothing.
                continue

            # Clears a stale hold whose window has since passed or been turned
            # off, so the field always reads as the current plan.
            if message.hold_until or message.hold_reason:
                message.write({'hold_until': False, 'hold_reason': False})
            message.action_process()

        if holds:
            # Wake exactly when the earliest hold expires, rather than leaving
            # held messages to wait out the cron's own interval.
            self._trigger_queue(at=max(min(holds), fields.Datetime.now()))
        return True

    @api.model
    def _trigger_event(self, model_name, record, event_code, rule_id=None):
        # rule_id is optional so the server actions written before scheduled
        # rules existed keep working untouched - which is why this change needs
        # no migration.
        from ..services.dispatcher import enqueue_event
        return enqueue_event(self.env, model_name, record, event_code, rule_id=rule_id)


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
