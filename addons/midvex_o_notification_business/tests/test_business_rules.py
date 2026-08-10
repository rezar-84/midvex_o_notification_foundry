from datetime import datetime

from odoo.tests.common import TransactionCase


class TestBusinessRules(TransactionCase):
    """The shipped templates and rules are data, so the thing worth testing is
    that they load wired up and that their domains select what they claim."""

    def _rule(self, xml_id):
        return self.env.ref('midvex_o_notification_business.%s' % xml_id)

    # Every event-driven rule that ships enabled. The scheduled pair is checked
    # separately below - base.automation has no 'on_schedule', so their
    # automations carry a different trigger by design.
    EVENT_RULES = (
        'rule_lead_assigned', 'rule_lead_won', 'rule_lead_lost',
        'rule_sale_confirmed',
        'rule_invoice_posted', 'rule_invoice_paid', 'rule_invoice_partially_paid',
        'rule_payment_received', 'rule_credit_note_issued', 'rule_invoice_cancelled',
        'rule_vendor_bill_posted', 'rule_vendor_bill_paid', 'rule_vendor_credit_note',
    )

    SCHEDULED_RULES = ('rule_invoice_due_soon', 'rule_invoice_overdue')

    def test_active_rules_are_wired_to_an_automation(self):
        """A rule with no automation matches nothing and reports no error,
        which is the failure this whole module would otherwise inherit."""
        for xml_id in self.EVENT_RULES:
            rule = self._rule(xml_id)
            self.assertTrue(rule.active, '%s should ship enabled' % xml_id)
            self.assertTrue(rule.automation_id, '%s is not wired to an automation' % xml_id)
            self.assertEqual(rule.automation_id.trigger, rule.trigger)
            self.assertEqual(rule.automation_id.model_id, rule.model_id)

    def test_the_lead_rules_share_one_automation(self):
        """Three rules, one trigger, one model - so one automation, or the
        dispatcher runs the whole set once per automation."""
        automations = {self._rule(x).automation_id
                        for x in ('rule_lead_assigned', 'rule_lead_won', 'rule_lead_lost')}
        self.assertEqual(len(automations), 1)

    def test_stage_changed_ships_disabled(self):
        """It fires on every write to a lead, not only on a stage change, so
        it is the noisiest rule here and is opt-in."""
        self.assertFalse(self._rule('rule_lead_stage_changed').active)

    def test_lost_rule_selects_archived_leads(self):
        """A lost lead is archived, so a domain that does not ask for inactive
        records explicitly would never match one."""
        rule = self._rule('rule_lead_lost')
        self.assertIn("('active', '=', False)", rule.trigger_domain)

    def test_invoice_rule_excludes_vendor_bills(self):
        """account.move covers bills and refunds too, and 'paid' on a vendor
        bill is money going out, not a sale."""
        domain = self._rule('rule_invoice_paid').trigger_domain
        self.assertIn("('move_type', '=', 'out_invoice')", domain)
        self.assertIn("('payment_state', '=', 'paid')", domain)

    def test_every_template_renders_against_a_real_record(self):
        """Placeholders are only checked when something renders them, so a
        typo in a field name would otherwise surface as a failed delivery."""
        lead = self.env['crm.lead'].create({'name': 'Render probe'})
        for xml_id in ('template_lead_assigned', 'template_lead_stage_changed',
                        'template_lead_won', 'template_lead_lost'):
            rendered = self.env.ref('midvex_o_notification_business.%s' % xml_id).render(lead)
            self.assertIn('Render probe', rendered['body'], xml_id)

    def test_sale_and_invoice_templates_render(self):
        partner = self.env['res.partner'].create({'name': 'Render Co'})
        order = self.env['sale.order'].create({'partner_id': partner.id})
        rendered = self.env.ref('midvex_o_notification_business.template_sale_confirmed').render(order)
        self.assertIn('Render Co', rendered['body'])

        invoice = self.env['account.move'].create({
            'move_type': 'out_invoice', 'partner_id': partner.id})
        for xml_id in ('template_invoice_posted', 'template_invoice_paid',
                        'template_invoice_partially_paid', 'template_invoice_due_soon',
                        'template_invoice_overdue', 'template_invoice_cancelled',
                        'template_high_value_invoice'):
            rendered = self.env.ref('midvex_o_notification_business.%s' % xml_id).render(invoice)
            self.assertIn('Render Co', rendered['body'], xml_id)

        credit_note = self.env['account.move'].create({
            'move_type': 'out_refund', 'partner_id': partner.id})
        rendered = self.env.ref(
            'midvex_o_notification_business.template_credit_note_issued').render(credit_note)
        self.assertIn('Render Co', rendered['body'])

    def test_vendor_templates_render(self):
        partner = self.env['res.partner'].create({'name': 'Supplier Co'})
        bill = self.env['account.move'].create({
            'move_type': 'in_invoice', 'partner_id': partner.id})
        for xml_id in ('template_vendor_bill_posted', 'template_vendor_bill_paid'):
            rendered = self.env.ref('midvex_o_notification_business.%s' % xml_id).render(bill)
            self.assertIn('Supplier Co', rendered['body'], xml_id)

        refund = self.env['account.move'].create({
            'move_type': 'in_refund', 'partner_id': partner.id})
        rendered = self.env.ref(
            'midvex_o_notification_business.template_vendor_credit_note').render(refund)
        self.assertIn('Supplier Co', rendered['body'])

    def test_the_payment_template_renders(self):
        """account.payment is the only non-account.move model here, so a field
        name borrowed from an invoice would go unnoticed until a real payment
        failed to deliver."""
        partner = self.env['res.partner'].create({'name': 'Paying Co'})
        payment = self.env['account.payment'].create({
            'payment_type': 'inbound', 'partner_type': 'customer',
            'partner_id': partner.id, 'amount': 250.0,
        })
        rendered = self.env.ref(
            'midvex_o_notification_business.template_payment_received').render(payment)
        self.assertIn('Paying Co', rendered['body'])

    # --- The accounting rules themselves --------------------------------------

    def test_customer_and_vendor_paid_rules_cannot_cross(self):
        """Both say "paid" and they mean opposite directions of cash. If either
        domain lost its move_type, one would swallow the other's records."""
        customer = self._rule('rule_invoice_paid').trigger_domain
        vendor = self._rule('rule_vendor_bill_paid').trigger_domain
        self.assertIn("('move_type', '=', 'out_invoice')", customer)
        self.assertIn("('move_type', '=', 'in_invoice')", vendor)

    def test_every_accounting_rule_pins_a_document_type(self):
        """account.move also carries plain journal entries. A rule without a
        move_type would alert on the ledger's own bookkeeping."""
        for xml_id in ('rule_invoice_posted', 'rule_invoice_paid',
                        'rule_invoice_partially_paid', 'rule_credit_note_issued',
                        'rule_invoice_cancelled', 'rule_high_value_invoice',
                        'rule_vendor_bill_posted', 'rule_vendor_bill_paid',
                        'rule_vendor_credit_note') + self.SCHEDULED_RULES:
            domain = self._rule(xml_id).trigger_domain or ''
            self.assertIn("'move_type'", domain, '%s does not pin a move_type' % xml_id)

    def test_the_high_value_rule_ships_disabled(self):
        """Its threshold is a placeholder, and a shipped guess either alerts on
        every invoice or never fires - which look identical from outside."""
        rule = self._rule('rule_high_value_invoice')
        self.assertFalse(rule.active)
        self.assertIn("('amount_total', '>=', 100000)", rule.trigger_domain)

    def test_the_scheduled_rules_watch_the_due_date(self):
        """These are the reason the rule model grew an on_schedule trigger:
        nobody writes to an invoice on the day it falls due."""
        for xml_id in self.SCHEDULED_RULES:
            rule = self._rule(xml_id)
            self.assertTrue(rule.active, '%s should ship enabled' % xml_id)
            self.assertEqual(rule.trigger, 'on_schedule')
            self.assertEqual(rule.date_field_id.name, 'invoice_date_due')
            self.assertEqual(rule.date_field_id.model, 'account.move')
            # Settled invoices drop out on their own rather than being chased.
            self.assertIn("'payment_state'", rule.trigger_domain)

    def test_the_scheduled_rules_do_not_share_an_automation(self):
        """One automation cannot describe two windows: the date field, the
        offset and the domain all live on it."""
        due_soon = self._rule('rule_invoice_due_soon')
        overdue = self._rule('rule_invoice_overdue')
        self.assertTrue(due_soon.automation_id)
        self.assertTrue(overdue.automation_id)
        self.assertNotEqual(due_soon.automation_id, overdue.automation_id)
        self.assertEqual(due_soon.automation_id.trg_date_range, 3)
        self.assertEqual(due_soon.automation_id.trg_date_range_mode, 'before')
        self.assertEqual(overdue.automation_id.trg_date_range, 1)
        self.assertEqual(overdue.automation_id.trg_date_range_mode, 'after')

    def test_the_scheduled_automations_do_not_start_in_1970(self):
        """base.automation fires every record whose date crossed between
        last_run and now. Left at the epoch, enabling these would enqueue every
        invoice ever overdue in one go."""
        for xml_id in self.SCHEDULED_RULES:
            automation = self._rule(xml_id).automation_id
            self.assertTrue(automation.last_run, '%s has no last_run' % xml_id)
            self.assertGreater(automation.last_run, datetime(2000, 1, 1), xml_id)
