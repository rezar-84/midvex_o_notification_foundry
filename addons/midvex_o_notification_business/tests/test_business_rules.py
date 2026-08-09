from odoo.tests.common import TransactionCase


class TestBusinessRules(TransactionCase):
    """The shipped templates and rules are data, so the thing worth testing is
    that they load wired up and that their domains select what they claim."""

    def _rule(self, xml_id):
        return self.env.ref('midvex_o_notification_business.%s' % xml_id)

    def test_active_rules_are_wired_to_an_automation(self):
        """A rule with no automation matches nothing and reports no error,
        which is the failure this whole module would otherwise inherit."""
        for xml_id in ('rule_lead_assigned', 'rule_lead_won', 'rule_lead_lost',
                        'rule_sale_confirmed', 'rule_invoice_paid'):
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
        rendered = self.env.ref('midvex_o_notification_business.template_invoice_paid').render(invoice)
        self.assertIn('Render Co', rendered['body'])
