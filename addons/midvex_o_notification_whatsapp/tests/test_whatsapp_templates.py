from odoo.tests.common import TransactionCase

from odoo.addons.midvex_o_notification_foundry.tests.common import ensure_channel

from . import fixtures


class TestWhatsAppTemplateMapping(TransactionCase):
    def setUp(self):
        super().setUp()
        self.channel = ensure_channel(self.env, 'whatsapp', 'WhatsApp')
        self.account = self.env['midvex.notification.account'].create({
            'name': 'Test WhatsApp',
            'channel_id': self.channel.id,
            'wa_phone_number_id': fixtures.PHONE_NUMBER_ID,
        })
        self.Mapping = self.env['midvex.notification.whatsapp.template']

    def _map(self, code='lead_created', language='en_US', name='vars_lead_created', **extra):
        return self.Mapping.create(dict({
            'account_id': self.account.id,
            'template_code': code,
            'language_code': language,
            'provider_template_name': name,
        }, **extra))

    # --- lookup --------------------------------------------------------

    def test_an_unmapped_template_finds_nothing(self):
        """Which is what makes the message go out as plain text.

        Not an error: inside the customer service window free text is exactly
        right, and requiring a mapping for every template would make the module
        unusable until every template had been through Meta's approval queue.
        """
        self.assertFalse(self.Mapping.find_for(self.account, 'lead_created', 'en_US'))

    def test_an_exact_language_match_wins(self):
        self._map(language='en_US', name='english_one')
        turkish = self._map(language='tr_TR', name='turkish_one')
        self.assertEqual(self.Mapping.find_for(self.account, 'lead_created', 'tr_TR'), turkish)

    def test_a_base_language_match_is_accepted(self):
        """Odoo says tr_TR; a template may have been approved as plain tr."""
        mapping = self._map(language='tr')
        self.assertEqual(self.Mapping.find_for(self.account, 'lead_created', 'tr_TR'), mapping)

    def test_a_hyphenated_language_is_understood(self):
        mapping = self._map(language='tr_TR')
        self.assertEqual(self.Mapping.find_for(self.account, 'lead_created', 'tr-TR'), mapping)

    def test_a_different_language_is_never_substituted(self):
        """The point of ADR-011 was that a Turkish recipient got English.

        Falling back to any available language here would reintroduce exactly
        that, but harder to notice — the body would be Turkish and the approved
        template around it English.
        """
        self._map(language='en_US')
        self.assertFalse(self.Mapping.find_for(self.account, 'lead_created', 'tr_TR'))

    def test_an_archived_mapping_is_not_used(self):
        self._map(active=False)
        self.assertFalse(self.Mapping.find_for(self.account, 'lead_created', 'en_US'))

    def test_another_accounts_mapping_is_not_used(self):
        """Templates are approved per WhatsApp Business Account.

        One company's approved template is not another's, and sending under a
        name the account never had approved fails at the provider.
        """
        other = self.env['midvex.notification.account'].create({
            'name': 'Second WhatsApp', 'channel_id': self.channel.id,
            'wa_phone_number_id': '300000000000003',
        })
        self._map()
        self.assertFalse(self.Mapping.find_for(other, 'lead_created', 'en_US'))

    def test_missing_arguments_find_nothing_rather_than_raising(self):
        self.assertFalse(self.Mapping.find_for(self.account, None, 'en_US'))
        self.assertFalse(self.Mapping.find_for(False, 'lead_created', 'en_US'))

    # --- payload -------------------------------------------------------

    def test_a_template_without_variables_has_no_components(self):
        payload = self._map().build_component_payload({'body': 'ignored'})
        self.assertEqual(payload, {'name': 'vars_lead_created',
                                    'language': {'code': 'en_US'}})

    def test_variables_are_substituted_in_the_declared_order(self):
        """Approved templates address variables positionally — {{1}}, {{2}}.

        There is no named form, so the order in this field is the order Meta
        substitutes them, and reversing it silently swaps two values.
        """
        mapping = self._map(body_variable_fields='subject,body')
        payload = mapping.build_component_payload({'subject': 'Acme', 'body': 'Hello'})
        self.assertEqual(payload['components'], [{
            'type': 'body',
            'parameters': [{'type': 'text', 'text': 'Acme'},
                            {'type': 'text', 'text': 'Hello'}],
        }])

    def test_a_missing_variable_becomes_empty_rather_than_raising(self):
        """A blank variable makes a slightly worse message.

        A traceback in the queue cron makes none at all, and takes every other
        queued message in the batch down with it.
        """
        mapping = self._map(body_variable_fields='subject,absent')
        payload = mapping.build_component_payload({'subject': 'Acme'})
        self.assertEqual(payload['components'][0]['parameters'][1], {'type': 'text', 'text': ''})

    def test_whitespace_in_the_variable_list_is_tolerated(self):
        mapping = self._map(body_variable_fields=' subject , body ')
        payload = mapping.build_component_payload({'subject': 'A', 'body': 'B'})
        self.assertEqual(len(payload['components'][0]['parameters']), 2)

    # --- constraints ---------------------------------------------------

    def test_one_mapping_per_template_and_language(self):
        from psycopg2 import IntegrityError
        self._map()
        with self.assertRaises(IntegrityError), self.env.cr.savepoint():
            self._map(name='a_second_one')

    def test_the_same_template_maps_once_per_language(self):
        self._map(language='en_US')
        self._map(language='tr_TR', name='turkish_one')
        self.assertEqual(self.Mapping.search_count([('account_id', '=', self.account.id)]), 2)


class TestWhatsAppTemplateSelection(TransactionCase):
    """The whole path from a queued message to the payload on the wire.

    The unit tests above prove find_for and build_component_payload in
    isolation. This proves the adapter joins them to the right language, which
    is where the interesting mistake lives: the body is rendered in the
    recipient's language (ADR-011), so looking the mapping up in any other one
    would wrap a Turkish body in an English-approved template.
    """

    def setUp(self):
        super().setUp()
        from ..services.whatsapp_adapter import WhatsAppAdapter

        self.channel = ensure_channel(self.env, 'whatsapp', 'WhatsApp')
        self.account = self.env['midvex.notification.account'].create({
            'name': 'Test WhatsApp', 'channel_id': self.channel.id,
            'wa_phone_number_id': fixtures.PHONE_NUMBER_ID,
        })
        self.user = self.env['res.users'].create({
            'name': 'Turkish Agent', 'login': 'wa_tr_agent', 'lang': 'en_US',
        })
        self.recipient = self.env['midvex.notification.recipient'].create({
            'kind': 'user', 'user_id': self.user.id, 'account_id': self.account.id,
            'external_id': '+%s' % fixtures.CUSTOMER_WA_ID, 'state': 'linked',
        })
        self.template = self.env['midvex.notification.template'].create({
            'name': 'Lead created', 'code': 'wa_lead_created',
            'model_id': self.env.ref('base.model_res_partner').id,
            'body': 'A new lead arrived.',
        })
        # No rule. action_process reads template_code off message.rule_id, but
        # the adapter only ever sees the DTO, so building one by hand exercises
        # the same path without dragging in base.automation.
        self.message = self.env['midvex.notification.message'].create({
            'name': 'Test', 'recipient_id': self.recipient.id, 'account_id': self.account.id,
            'body': 'A new lead arrived.', 'subject': 'Acme Ltd',
            'idempotency_key': 'wa-tpl-1',
        })

        self.adapter = WhatsAppAdapter()
        self.sent = []
        self.adapter.client.send_message = lambda account, payload: (
            self.sent.append(payload) or fixtures.send_success())

    def dto(self):
        return {
            'message_id': self.message.id,
            'recipient_external_id': self.recipient.external_id,
            'subject': self.message.subject,
            'body': self.message.body,
            'template_code': self.template.code,
            'res_model': False, 'res_id': False, 'variables': {},
        }

    def test_without_a_mapping_the_message_goes_as_text(self):
        self.adapter.send(self.account, self.dto())
        self.assertEqual(self.sent[0]['type'], 'text')
        self.assertEqual(self.sent[0]['text']['body'], 'A new lead arrived.')

    def test_with_a_mapping_the_message_goes_as_that_template(self):
        self.env['midvex.notification.whatsapp.template'].create({
            'account_id': self.account.id, 'template_code': 'wa_lead_created',
            'language_code': 'en_US', 'provider_template_name': 'vars_lead_created',
            'body_variable_fields': 'subject',
        })
        self.adapter.send(self.account, self.dto())
        self.assertEqual(self.sent[0]['type'], 'template')
        self.assertEqual(self.sent[0]['template']['name'], 'vars_lead_created')
        self.assertEqual(self.sent[0]['template']['language']['code'], 'en_US')
        self.assertEqual(
            self.sent[0]['template']['components'][0]['parameters'],
            [{'type': 'text', 'text': 'Acme Ltd'}])

    def test_the_mapping_is_looked_up_in_the_recipients_language(self):
        """Not the acting user's, and not the database default.

        This is the same mistake ADR-011 fixed for rendering, one layer up: the
        body would be Turkish and the approved template around it English.
        """
        self.env['res.lang']._activate_lang('tr_TR')
        self.user.lang = 'tr_TR'
        for language, name in (('en_US', 'english_one'), ('tr_TR', 'turkish_one')):
            self.env['midvex.notification.whatsapp.template'].create({
                'account_id': self.account.id, 'template_code': 'wa_lead_created',
                'language_code': language, 'provider_template_name': name,
            })
        self.adapter.send(self.account, self.dto())
        self.assertEqual(self.sent[0]['template']['name'], 'turkish_one')

    def test_a_message_with_no_template_code_never_looks_one_up(self):
        self.env['midvex.notification.whatsapp.template'].create({
            'account_id': self.account.id, 'template_code': 'wa_lead_created',
            'language_code': 'en_US', 'provider_template_name': 'vars_lead_created',
        })
        dto = dict(self.dto(), template_code=False)
        self.adapter.send(self.account, dto)
        self.assertEqual(self.sent[0]['type'], 'text')

    def test_a_group_recipient_falls_back_rather_than_failing(self):
        """A shared chat has no user, so it has no language of its own.

        Group recipients are a Telegram idea and unlikely on WhatsApp, but the
        model allows them and a lookup that raised here would take down the
        queue for everyone else in the batch.
        """
        group = self.env['midvex.notification.recipient'].create({
            'kind': 'group', 'name': 'Shared', 'account_id': self.account.id,
            'external_id': '+905222222222', 'state': 'linked',
        })
        message = self.env['midvex.notification.message'].create({
            'name': 'Test', 'recipient_id': group.id, 'account_id': self.account.id,
            'body': 'Hello', 'idempotency_key': 'wa-tpl-2',
        })
        dto = dict(self.dto(), message_id=message.id,
                   recipient_external_id=group.external_id)
        self.adapter.send(self.account, dto)
        self.assertTrue(self.sent)
