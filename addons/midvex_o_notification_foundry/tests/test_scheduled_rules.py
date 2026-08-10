from datetime import datetime

from odoo import fields
from odoo.exceptions import ValidationError
from odoo.tests.common import TransactionCase

from .common import ensure_channel


class TestScheduledRules(TransactionCase):
    """A scheduled rule reacts to a date passing rather than to somebody saving
    a record, which is the only way to say "this invoice is now overdue".

    res.partner is the model under test throughout: it needs nothing beyond
    base, and it carries two date fields to point a rule at.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.channel = ensure_channel(cls.env, 'notification_sched', 'Scheduled Test Channel')
        cls.partner_model = cls.env['ir.model']._get('res.partner')
        # create_date rather than a business date: it is present on every model
        # in every database, so these tests do not depend on which apps happen
        # to be installed.
        cls.date_field = cls.env['ir.model.fields']._get('res.partner', 'create_date')
        cls.template = cls.env['midvex.notification.template'].create({
            'name': 'Partner date reached', 'code': 'sched_partner_date',
            'model_id': cls.partner_model.id, 'body': '{{ object.name }} reached its date',
        })

    def _rule(self, name, offset=0, mode='after', domain=None, date_field=None):
        return self.env['midvex.notification.rule'].create({
            'name': name,
            'model_id': self.partner_model.id,
            'trigger': 'on_schedule',
            'date_field_id': (date_field or self.date_field).id,
            'schedule_offset': offset,
            'schedule_offset_mode': mode,
            'trigger_domain': domain,
            'template_id': self.template.id,
            'channel_ids': [(4, self.channel.id)],
        })

    # --- Automation wiring ---------------------------------------------------

    def test_a_scheduled_rule_describes_itself_to_base_automation(self):
        """The whole window lives on the automation, so anything not copied
        across is a setting the cron never sees."""
        rule = self._rule('Overdue partners', offset=3, mode='before',
                           domain="[('active', '=', True)]")
        automation = rule.automation_id
        self.assertTrue(automation)
        # base.automation has no 'on_schedule'; its time-based trigger is on_time.
        self.assertEqual(automation.trigger, 'on_time')
        self.assertEqual(automation.trg_date_id, self.date_field)
        self.assertEqual(automation.trg_date_range, 3)
        self.assertEqual(automation.trg_date_range_mode, 'before')
        self.assertEqual(automation.trg_date_range_type, 'day')
        self.assertEqual(automation.filter_domain, "[('active', '=', True)]")

    def test_each_scheduled_rule_owns_its_automation(self):
        """Create/update rules share one automation per (model, trigger) because
        the dispatcher already walks the whole set. Scheduled rules cannot: the
        date field, the offset and the domain all live on the automation, so one
        record cannot describe two rules."""
        due_soon = self._rule('Due soon', offset=3, mode='before')
        overdue = self._rule('Overdue', offset=1, mode='after')
        self.assertTrue(due_soon.automation_id)
        self.assertTrue(overdue.automation_id)
        self.assertNotEqual(due_soon.automation_id, overdue.automation_id)

    def test_the_server_action_names_the_rule(self):
        """Without the rule id in the call, the automation for "due soon" would
        also enqueue "overdue" for any record both domains match."""
        rule = self._rule('Named rule')
        codes = rule.automation_id.action_server_ids.mapped('code')
        self.assertTrue(any('rule_id=%d' % rule.id in (code or '') for code in codes),
                         'the server action does not identify its rule: %s' % codes)

    def test_last_run_is_stamped_at_creation(self):
        """base.automation defaults last_run to the epoch and fires every record
        whose date crossed between last_run and now. Left alone, switching a rule
        on would treat every invoice overdue since 1970 as newly due."""
        before = fields.Datetime.now()
        rule = self._rule('Backfill guard')
        self.assertTrue(rule.automation_id.last_run)
        self.assertGreaterEqual(rule.automation_id.last_run, before)
        self.assertGreater(rule.automation_id.last_run, datetime(2000, 1, 1))

    def test_editing_the_window_reaches_the_automation(self):
        """A rule edited in the UI whose automation kept the old offset would
        keep firing on the old schedule, silently."""
        rule = self._rule('Movable', offset=1, mode='after')
        rule.write({'schedule_offset': 7, 'schedule_offset_mode': 'before',
                     'trigger_domain': "[('active', '=', False)]"})
        self.assertEqual(rule.automation_id.trg_date_range, 7)
        self.assertEqual(rule.automation_id.trg_date_range_mode, 'before')
        self.assertEqual(rule.automation_id.filter_domain, "[('active', '=', False)]")

    def test_archiving_one_rule_leaves_its_sibling_running(self):
        """The orphan sweep counts rules by (model, trigger), which cannot see a
        per-rule automation: two scheduled rules on one model would otherwise
        keep each other's automations alive forever, or drop them together."""
        due_soon = self._rule('Due soon', offset=3, mode='before')
        overdue = self._rule('Overdue', offset=1, mode='after')
        survivor = overdue.automation_id
        due_soon.active = False
        self.assertFalse(due_soon.automation_id)
        self.assertTrue(survivor.exists())
        self.assertEqual(overdue.automation_id, survivor)

    def test_a_scheduled_rule_needs_a_date_field(self):
        with self.assertRaises(ValidationError):
            self.env['midvex.notification.rule'].create({
                'name': 'No date', 'model_id': self.partner_model.id, 'trigger': 'on_schedule',
                'template_id': self.template.id, 'channel_ids': [(4, self.channel.id)],
            })

    def test_the_date_field_must_belong_to_the_model(self):
        """Pointing at another model's field yields an automation the cron
        cannot use, and it logs a warning rather than failing."""
        other = self.env['ir.model.fields']._get('res.company', 'create_date')
        with self.assertRaises(ValidationError):
            self._rule('Wrong model', date_field=other)


class TestScheduledDispatch(TransactionCase):
    """What the cron's server action does once base.automation has picked the
    records: which rules run, and how often the same record can alert."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.channel = ensure_channel(cls.env, 'notification_sched_disp', 'Scheduled Dispatch Channel')
        cls.account = cls.env['midvex.notification.account'].create({
            'name': 'Scheduled account', 'channel_id': cls.channel.id, 'state': 'connected',
        })
        cls.member = cls.env['res.users'].create({
            'name': 'Scheduled Member', 'login': 'notif_sched_member',
            'email': 'sched@example.com',
        })
        cls.env['midvex.notification.recipient'].create({
            'user_id': cls.member.id, 'account_id': cls.account.id,
            'state': 'linked', 'external_id': 'chat-sched',
        })
        cls.partner_model = cls.env['ir.model']._get('res.partner')
        # create_date rather than a business date: it is present on every model
        # in every database, so these tests do not depend on which apps happen
        # to be installed.
        cls.date_field = cls.env['ir.model.fields']._get('res.partner', 'create_date')
        cls.Message = cls.env['midvex.notification.message']

    def _rule(self, name, body):
        template = self.env['midvex.notification.template'].create({
            'name': name, 'code': name.lower().replace(' ', '_'),
            'model_id': self.partner_model.id, 'body': body,
        })
        return self.env['midvex.notification.rule'].create({
            'name': name, 'model_id': self.partner_model.id, 'trigger': 'on_schedule',
            'date_field_id': self.date_field.id, 'template_id': template.id,
            'channel_ids': [(4, self.channel.id)],
            'audience_user_ids': [(4, self.member.id)],
        })

    def test_a_scheduled_event_runs_only_the_rule_that_asked(self):
        """"Due soon" and "overdue" watch the same model with overlapping
        domains. Without the rule id, either automation firing would enqueue
        both, and every invoice would be called overdue three days early."""
        due_soon = self._rule('Due soon', 'due soon: {{ object.name }}')
        self._rule('Overdue', 'overdue: {{ object.name }}')
        partner = self.env['res.partner'].create({'name': 'Late Payer'})

        created = self.Message._trigger_event('res.partner', partner, 'scheduled',
                                               rule_id=due_soon.id)
        self.assertEqual(len(created), 1)
        self.assertEqual(created.rule_id, due_soon)
        self.assertEqual(created.body, 'due soon: Late Payer')

    def test_a_scheduled_rule_notifies_a_record_once(self):
        """An on-update rule discriminates occurrences by write_date so it can
        fire on every change. A scheduled rule must not: an automation recreated
        with a reset last_run would otherwise re-send its whole backlog."""
        rule = self._rule('Once only', 'once: {{ object.name }}')
        partner = self.env['res.partner'].create({'name': 'Repeat Candidate'})

        first = self.Message._trigger_event('res.partner', partner, 'scheduled', rule_id=rule.id)
        self.assertEqual(len(first), 1)
        partner.write({'comment': 'touched, so write_date has moved'})
        second = self.Message._trigger_event('res.partner', partner, 'scheduled', rule_id=rule.id)
        self.assertEqual(len(second), 0)

    def test_the_domain_still_applies(self):
        rule = self._rule('Filtered', 'filtered: {{ object.name }}')
        rule.trigger_domain = "[('is_company', '=', True)]"
        person = self.env['res.partner'].create({'name': 'A Person', 'is_company': False})
        self.assertEqual(
            len(self.Message._trigger_event('res.partner', person, 'scheduled', rule_id=rule.id)), 0)
