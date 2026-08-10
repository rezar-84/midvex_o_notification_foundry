from datetime import datetime, timedelta

from odoo import fields
from odoo.exceptions import ValidationError
from odoo.tests.common import TransactionCase

from ..services import registry
from .common import ensure_channel


class MockAdapter:
    channel_code = 'notification_mock'

    def __init__(self):
        self.send_calls = []

    def test_connection(self, account):
        return {'ok': True}

    def send(self, account, message_dto):
        self.send_calls.append(message_dto)
        return {'ok': True, 'provider_message_id': 'mock-%s' % len(self.send_calls)}

    def register_webhook(self, account, webhook_url, secret_token):
        return {'ok': True}

    def parse_inbound(self, raw_payload):
        return {}

    def parse_error(self, response_or_exception):
        return {'error_code': 'UNKNOWN', 'message': str(response_or_exception), 'retryable': False}


class TestNotificationDispatchMocked(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.adapter = MockAdapter()
        registry._ADAPTERS[cls.adapter.channel_code] = cls.adapter
        cls.channel = ensure_channel(cls.env, cls.adapter.channel_code, 'Mock Channel')
        cls.account = cls.env['midvex.notification.account'].create({
            'name': 'Mock account', 'channel_id': cls.channel.id, 'state': 'connected',
        })
        # TransactionCase's default env.user is the inactive system user; Many2many reads to
        # res.users apply an implicit active_test filter, so a dedicated active user is needed
        # as the audience member here rather than cls.env.user.
        cls.member = cls.env['res.users'].create({
            'name': 'Dispatch Member', 'login': 'notif_dispatch_member', 'email': 'dispatch@example.com',
        })
        cls.recipient = cls.env['midvex.notification.recipient'].create({
            'user_id': cls.member.id, 'account_id': cls.account.id,
            'state': 'linked', 'external_id': 'chat-1',
        })
        partner_model = cls.env['ir.model']._get('res.partner')
        cls.template = cls.env['midvex.notification.template'].create({
            'name': 'Partner created', 'code': 'partner_created', 'model_id': partner_model.id,
            'subject': 'New partner', 'body': '{{ object.name }} was created',
        })
        cls.rule = cls.env['midvex.notification.rule'].create({
            'name': 'Notify on partner creation', 'model_id': partner_model.id, 'trigger': 'on_create',
            'template_id': cls.template.id, 'channel_ids': [(4, cls.channel.id)],
            'audience_user_ids': [(4, cls.member.id)],
        })

    @classmethod
    def tearDownClass(cls):
        registry.unregister_adapter(cls.adapter.channel_code)
        super().tearDownClass()

    def test_event_enqueues_and_processes_a_message(self):
        partner = self.env['res.partner'].create({'name': 'Acme Corp'})
        Message = self.env['midvex.notification.message']
        created = Message._trigger_event('res.partner', partner, 'created')
        self.assertEqual(len(created), 1)
        self.assertEqual(created.body, 'Acme Corp was created')
        self.assertEqual(created.state, 'pending')

        created.action_process()
        self.assertEqual(created.state, 'sent')
        self.assertEqual(len(self.adapter.send_calls), 1)
        self.assertEqual(self.adapter.send_calls[0]['recipient_external_id'], 'chat-1')

        log = self.env['midvex.notification.log'].search([('message_id', '=', created.id)])
        self.assertEqual(log.status, 'success')

    def test_duplicate_trigger_does_not_create_a_second_message(self):
        partner = self.env['res.partner'].create({'name': 'Beta LLC'})
        Message = self.env['midvex.notification.message']
        first = Message._trigger_event('res.partner', partner, 'created')
        second = Message._trigger_event('res.partner', partner, 'created')
        self.assertEqual(len(second), 0)
        messages = Message.search([('res_model', '=', 'res.partner'), ('res_id', '=', partner.id)])
        self.assertEqual(len(messages), 1)
        self.assertEqual(messages, first)

    def test_unlinked_recipient_is_skipped(self):
        self.recipient.write({'state': 'pending'})
        partner = self.env['res.partner'].create({'name': 'Gamma Inc'})
        created = self.env['midvex.notification.message']._trigger_event('res.partner', partner, 'created')
        self.assertEqual(len(created), 0)
        self.recipient.write({'state': 'linked'})


class TestGroupChatRecipients(TransactionCase):
    """A shared chat is a destination in its own right, not somebody's link."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.adapter = MockAdapter()
        registry._ADAPTERS[cls.adapter.channel_code] = cls.adapter
        cls.channel = ensure_channel(cls.env, cls.adapter.channel_code, 'Mock Channel')
        cls.account = cls.env['midvex.notification.account'].create({
            'name': 'Group account', 'channel_id': cls.channel.id, 'state': 'connected',
        })
        cls.room = cls.env['midvex.notification.recipient'].create({
            'kind': 'group', 'name': 'Sales room', 'account_id': cls.account.id,
            'state': 'linked', 'external_id': '-100999',
        })
        partner_model = cls.env['ir.model']._get('res.partner')
        cls.template = cls.env['midvex.notification.template'].create({
            'name': 'Partner created', 'code': 'group_partner_created',
            'model_id': partner_model.id, 'body': '{{ object.name }} was created',
        })
        cls.rule = cls.env['midvex.notification.rule'].create({
            'name': 'Notify the sales room', 'model_id': partner_model.id,
            'trigger': 'on_create', 'template_id': cls.template.id,
            'channel_ids': [(4, cls.channel.id)],
            'audience_recipient_ids': [(4, cls.room.id)],
        })

    @classmethod
    def tearDownClass(cls):
        registry.unregister_adapter(cls.adapter.channel_code)
        super().tearDownClass()

    def test_a_group_chat_needs_no_user(self):
        self.assertFalse(self.room.user_id)
        self.assertEqual(self.room.display_name, 'Sales room')

    def test_a_group_chat_may_not_carry_a_user(self):
        """The dispatcher resolves user recipients by user_id, so a group chat
        holding one would receive that person's private alerts."""
        user = self.env['res.users'].create({'name': 'Nina', 'login': 'group_nina'})
        with self.assertRaises(ValidationError):
            self.room.write({'user_id': user.id})

    def test_a_user_recipient_still_needs_a_user(self):
        with self.assertRaises(ValidationError):
            self.env['midvex.notification.recipient'].create({
                'kind': 'user', 'account_id': self.account.id,
            })

    def test_one_account_serves_several_rooms(self):
        """UNIQUE (account_id, user_id) must not collapse group chats onto one
        row: Postgres treats NULLs as distinct, and we rely on that."""
        second = self.env['midvex.notification.recipient'].create({
            'kind': 'group', 'name': 'Ops room', 'account_id': self.account.id,
            'state': 'linked', 'external_id': '-100888',
        })
        self.assertNotEqual(second, self.room)

    def test_rule_delivers_to_the_room(self):
        partner = self.env['res.partner'].create({'name': 'Delta Ltd'})
        created = self.env['midvex.notification.message']._trigger_event(
            'res.partner', partner, 'created')
        self.assertEqual(len(created), 1)
        self.assertEqual(created.recipient_id, self.room)
        self.assertEqual(created.body, 'Delta Ltd was created')

    def test_a_muted_room_is_not_enqueued(self):
        self.room.action_set_muted(True)
        partner = self.env['res.partner'].create({'name': 'Epsilon Ltd'})
        created = self.env['midvex.notification.message']._trigger_event(
            'res.partner', partner, 'created')
        self.assertEqual(len(created), 0)
        self.room.action_set_muted(False)

    def test_an_archived_room_is_not_enqueued(self):
        """Archiving is the off switch: Odoo drops inactive records from
        relational reads, so the rule stops seeing it."""
        self.room.write({'active': False})
        partner = self.env['res.partner'].create({'name': 'Zeta Ltd'})
        created = self.env['midvex.notification.message']._trigger_event(
            'res.partner', partner, 'created')
        self.assertEqual(len(created), 0)
        self.room.write({'active': True})

    def test_a_room_and_a_user_both_get_their_own_message(self):
        """Their idempotency keys must not collide, or whichever is enqueued
        second is silently swallowed as a duplicate."""
        member = self.env['res.users'].create({'name': 'Omar', 'login': 'group_omar'})
        self.env['midvex.notification.recipient'].create({
            'user_id': member.id, 'account_id': self.account.id,
            'state': 'linked', 'external_id': 'chat-omar',
        })
        self.rule.write({'audience_user_ids': [(4, member.id)]})
        partner = self.env['res.partner'].create({'name': 'Theta Ltd'})
        created = self.env['midvex.notification.message']._trigger_event(
            'res.partner', partner, 'created')
        self.assertEqual(len(created), 2)
        self.assertEqual(len(created.mapped('idempotency_key')), 2)


class TestQuietHours(TransactionCase):
    """Quiet hours hold delivery until the window ends; they never drop it."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.adapter = MockAdapter()
        registry._ADAPTERS[cls.adapter.channel_code] = cls.adapter
        cls.channel = ensure_channel(cls.env, cls.adapter.channel_code, 'Mock Channel')
        cls.account = cls.env['midvex.notification.account'].create({
            'name': 'Quiet account', 'channel_id': cls.channel.id, 'state': 'connected',
        })
        cls.room = cls.env['midvex.notification.recipient'].create({
            'kind': 'group', 'name': 'Night room', 'account_id': cls.account.id,
            'state': 'linked', 'external_id': '-100777',
            'quiet_enabled': True, 'quiet_start': 22.0, 'quiet_end': 7.0,
            'tz': 'Europe/Istanbul',
        })
        partner_model = cls.env['ir.model']._get('res.partner')
        cls.template = cls.env['midvex.notification.template'].create({
            'name': 'Partner created', 'code': 'quiet_partner_created',
            'model_id': partner_model.id, 'body': '{{ object.name }} was created',
        })
        cls.rule = cls.env['midvex.notification.rule'].create({
            'name': 'Notify the night room', 'model_id': partner_model.id,
            'trigger': 'on_create', 'template_id': cls.template.id,
            'channel_ids': [(4, cls.channel.id)],
            'audience_recipient_ids': [(4, cls.room.id)],
        })

    @classmethod
    def tearDownClass(cls):
        registry.unregister_adapter(cls.adapter.channel_code)
        super().tearDownClass()

    def test_disabled_quiet_hours_never_hold(self):
        self.room.quiet_enabled = False
        self.assertFalse(self.room._quiet_release_at(datetime(2026, 6, 1, 0, 0)))
        self.room.quiet_enabled = True

    def test_inside_a_window_that_crosses_midnight(self):
        """22:00-07:00 is the ordinary case, and the one a naive
        start <= t < end comparison gets backwards."""
        # 00:30 Istanbul (UTC+3) on 1 June 2026 == 21:30 UTC on 31 May.
        release = self.room._quiet_release_at(datetime(2026, 5, 31, 21, 30))
        self.assertTrue(release)
        # Releases at 07:00 Istanbul the same morning == 04:00 UTC.
        self.assertEqual(release, datetime(2026, 6, 1, 4, 0))

    def test_late_evening_releases_the_next_morning(self):
        # 23:00 Istanbul == 20:00 UTC, so the release rolls to the next day.
        release = self.room._quiet_release_at(datetime(2026, 6, 1, 20, 0))
        self.assertEqual(release, datetime(2026, 6, 2, 4, 0))

    def test_outside_the_window_is_not_quiet(self):
        # 12:00 Istanbul == 09:00 UTC.
        self.assertFalse(self.room._quiet_release_at(datetime(2026, 6, 1, 9, 0)))

    def test_boundaries_are_start_inclusive_and_end_exclusive(self):
        self.assertTrue(self.room._quiet_release_at(datetime(2026, 6, 1, 19, 0)))   # 22:00 local
        self.assertFalse(self.room._quiet_release_at(datetime(2026, 6, 1, 4, 0)))   # 07:00 local

    def test_a_daytime_window_does_not_wrap(self):
        self.room.write({'quiet_start': 9.0, 'quiet_end': 17.0})
        self.assertTrue(self.room._quiet_release_at(datetime(2026, 6, 1, 9, 0)))    # 12:00 local
        self.assertFalse(self.room._quiet_release_at(datetime(2026, 6, 1, 20, 0)))  # 23:00 local
        self.room.write({'quiet_start': 22.0, 'quiet_end': 7.0})

    def test_an_empty_window_means_off_not_permanently_quiet(self):
        """Both bounds equal must not silence a recipient forever."""
        self.room.write({'quiet_start': 8.0, 'quiet_end': 8.0})
        self.assertFalse(self.room._quiet_release_at(datetime(2026, 6, 1, 5, 0)))
        self.room.write({'quiet_start': 22.0, 'quiet_end': 7.0})

    def test_timezone_is_the_recipients_not_the_servers(self):
        """The same instant is quiet in one timezone and not in another."""
        self.room.tz = 'America/Los_Angeles'
        self.assertFalse(self.room._quiet_release_at(datetime(2026, 5, 31, 21, 30)))
        self.room.tz = 'Europe/Istanbul'

    def test_cron_holds_a_message_instead_of_sending_it(self):
        partner = self.env['res.partner'].create({'name': 'Nightly Ltd'})
        created = self.env['midvex.notification.message']._trigger_event(
            'res.partner', partner, 'created')
        self.assertEqual(len(created), 1)
        sends_before = len(self.adapter.send_calls)

        # A hold in the future, not one derived from a fixed date: an earlier
        # version of this test computed the release from 31 May and passed only
        # because the suite happened to run late at night, when the recipient's
        # window was open. The cron reads the real clock, so anything it is
        # asked to compare against has to be anchored to the real clock too.
        created.hold_until = fields.Datetime.now() + timedelta(hours=2)
        self.env['midvex.notification.message'].cron_process_pending()
        self.assertEqual(created.state, 'pending')
        self.assertEqual(len(self.adapter.send_calls), sends_before)

    def test_a_held_message_is_sent_once_the_window_passes(self):
        partner = self.env['res.partner'].create({'name': 'Morning Ltd'})
        created = self.env['midvex.notification.message']._trigger_event(
            'res.partner', partner, 'created')
        created.hold_until = datetime(2020, 1, 1, 0, 0)  # a hold that has expired
        self.room.quiet_enabled = False
        self.env['midvex.notification.message'].cron_process_pending()
        self.assertEqual(created.state, 'sent')
        # The stale hold is cleared, so the field always reads as the plan.
        self.assertFalse(created.hold_until)
        self.room.quiet_enabled = True

    def test_manual_retry_ignores_a_hold(self):
        """Pressing Retry is an explicit decision to interrupt; leaving the
        hold on would make the button look broken."""
        partner = self.env['res.partner'].create({'name': 'Urgent Ltd'})
        created = self.env['midvex.notification.message']._trigger_event(
            'res.partner', partner, 'created')
        created.write({'state': 'failed', 'hold_until': datetime(2099, 1, 1, 0, 0)})
        created.action_retry()
        self.assertEqual(created.state, 'sent')
        self.assertFalse(created.hold_until)

    def test_cron_sets_the_hold_and_logs_it_once(self):
        """Covers the branch that puts a message on hold, which the tests above
        cannot reach: the cron reads the real clock, so the window is built
        around it — one hour either side of now, in UTC — rather than hoping
        the suite runs at a convenient time of day."""
        now = fields.Datetime.now()
        minutes = now.hour * 60 + now.minute
        self.room.write({
            'tz': 'UTC',
            'quiet_start': ((minutes - 60) % 1440) / 60.0,
            'quiet_end': ((minutes + 60) % 1440) / 60.0,
        })
        partner = self.env['res.partner'].create({'name': 'Held Ltd'})
        created = self.env['midvex.notification.message']._trigger_event(
            'res.partner', partner, 'created')
        sends_before = len(self.adapter.send_calls)

        self.env['midvex.notification.message'].cron_process_pending()
        self.assertEqual(created.state, 'pending')
        self.assertTrue(created.hold_until, 'the cron did not put the message on hold')
        self.assertEqual(len(self.adapter.send_calls), sends_before, 'it was sent anyway')

        Log = self.env['midvex.notification.log']
        held_logs = Log.search([('message_id', '=', created.id), ('error_code', '=', 'QUIET_HOURS')])
        self.assertEqual(len(held_logs), 1)
        # A second pass must not log again, or the history fills with one line
        # per message per cron tick.
        self.env['midvex.notification.message'].cron_process_pending()
        self.assertEqual(len(Log.search([('message_id', '=', created.id),
                                          ('error_code', '=', 'QUIET_HOURS')])), 1)
        self.room.write({'quiet_start': 22.0, 'quiet_end': 7.0, 'tz': 'Europe/Istanbul'})

    def test_channel_code_follows_the_account_and_cannot_be_typed(self):
        """It was free text, so the queue could hold a channel no adapter
        answers to - the live instance ended up with rows coded '1'. Deriving
        it from the account makes that unrepresentable, and because the field
        is stored-related it recomputes on upgrade, repairing bad rows."""
        partner = self.env['res.partner'].create({'name': 'Coded Ltd'})
        self.room.quiet_enabled = False
        created = self.env['midvex.notification.message']._trigger_event(
            'res.partner', partner, 'created')
        self.assertEqual(created.channel_code, self.account.channel_code)

        # Readonly, so the form renders it as text rather than an input and
        # the '1' cannot be typed in again.
        self.assertTrue(self.env['midvex.notification.message']._fields['channel_code'].readonly)

        # A direct ORM write still lands on the message's own column - related
        # does not make a field immune - but it must not reach through and
        # rewrite the account's channel, which would break every other message
        # sent through that account.
        created.write({'channel_code': '1'})
        created.invalidate_recordset()
        self.assertEqual(self.account.channel_code, self.adapter.channel_code)
        self.room.quiet_enabled = True


class TestRuleWiring(TransactionCase):
    """A rule only fires because a base.automation on its model calls the
    dispatcher. Before this, the single automation that existed was written by
    hand in a data file, so any rule added through the UI matched nothing and
    said nothing about it."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.adapter = MockAdapter()
        registry._ADAPTERS[cls.adapter.channel_code] = cls.adapter
        cls.channel = ensure_channel(cls.env, cls.adapter.channel_code, 'Mock Channel')
        cls.partner_model = cls.env['ir.model']._get('res.partner')
        cls.template = cls.env['midvex.notification.template'].create({
            'name': 'Wiring', 'code': 'wiring_partner',
            'model_id': cls.partner_model.id, 'body': '{{ object.name }}',
        })

    @classmethod
    def tearDownClass(cls):
        registry.unregister_adapter(cls.adapter.channel_code)
        super().tearDownClass()

    def _rule(self, trigger='on_create', **values):
        return self.env['midvex.notification.rule'].create(dict({
            'name': 'R', 'model_id': self.partner_model.id, 'trigger': trigger,
            'template_id': self.template.id, 'channel_ids': [(4, self.channel.id)],
        }, **values))

    def test_creating_a_rule_wires_an_automation(self):
        rule = self._rule()
        self.assertTrue(rule.automation_id, 'the rule was not wired to anything')
        self.assertEqual(rule.automation_id.model_id, self.partner_model)
        self.assertEqual(rule.automation_id.trigger, 'on_create')
        action = rule.automation_id.action_server_ids
        self.assertTrue(action)
        self.assertIn('_trigger_event', action[0].code)
        self.assertIn('res.partner', action[0].code)

    def test_two_rules_on_one_model_share_one_automation(self):
        """enqueue_event already walks every matching rule, so a second
        automation would run the whole set a second time."""
        first, second = self._rule(), self._rule()
        self.assertEqual(first.automation_id, second.automation_id)

    def test_a_different_trigger_gets_its_own_automation(self):
        on_create, on_write = self._rule('on_create'), self._rule('on_write')
        self.assertNotEqual(on_create.automation_id, on_write.automation_id)
        self.assertEqual(on_write.automation_id.trigger, 'on_write')

    def test_an_existing_automation_is_adopted_not_duplicated(self):
        """Production already carries a hand-written automation for crm.lead;
        wiring must attach to it rather than double it up."""
        existing = self.env['base.automation'].create({
            'name': 'Hand written', 'model_id': self.partner_model.id, 'trigger': 'on_create',
        })
        rule = self._rule()
        self.assertEqual(rule.automation_id, existing)

    def test_deleting_the_last_rule_removes_the_automation(self):
        rule = self._rule()
        automation = rule.automation_id
        rule.unlink()
        self.assertFalse(automation.exists())

    def test_a_second_rule_keeps_the_automation_alive(self):
        first, second = self._rule(), self._rule()
        automation = first.automation_id
        first.unlink()
        self.assertTrue(automation.exists())
        self.assertEqual(second.automation_id, automation)

    def test_an_unrelated_automation_is_never_deleted(self):
        """Cleanup is scoped to automations running our own code, so someone
        else's automation on the same model survives."""
        theirs = self.env['base.automation'].create({
            'name': 'Theirs', 'model_id': self.env['ir.model']._get('res.users').id,
            'trigger': 'on_create',
        })
        rule = self._rule()
        rule.unlink()
        self.assertTrue(theirs.exists())


class TestOnWriteIsNotDedupedForever(TransactionCase):
    """An on_write rule fires on every change. Keyed only on the record it
    would notify once, ever, and then silently dedupe itself for good."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.adapter = MockAdapter()
        registry._ADAPTERS[cls.adapter.channel_code] = cls.adapter
        cls.channel = ensure_channel(cls.env, cls.adapter.channel_code, 'Mock Channel')
        cls.account = cls.env['midvex.notification.account'].create({
            'name': 'Write account', 'channel_id': cls.channel.id, 'state': 'connected',
        })
        cls.room = cls.env['midvex.notification.recipient'].create({
            'kind': 'group', 'name': 'Write room', 'account_id': cls.account.id,
            'state': 'linked', 'external_id': '-100666',
        })
        partner_model = cls.env['ir.model']._get('res.partner')
        cls.template = cls.env['midvex.notification.template'].create({
            'name': 'Changed', 'code': 'write_partner',
            'model_id': partner_model.id, 'body': '{{ object.name }} changed',
        })
        cls.rule = cls.env['midvex.notification.rule'].create({
            'name': 'On change', 'model_id': partner_model.id, 'trigger': 'on_write',
            'template_id': cls.template.id, 'channel_ids': [(4, cls.channel.id)],
            'audience_recipient_ids': [(4, cls.room.id)],
        })

    @classmethod
    def tearDownClass(cls):
        registry.unregister_adapter(cls.adapter.channel_code)
        super().tearDownClass()

    def test_each_change_notifies_again(self):
        Message = self.env['midvex.notification.message']
        partner = self.env['res.partner'].create({'name': 'Shifting Ltd'})

        partner.write({'name': 'Shifting Ltd A'})
        first = Message._trigger_event('res.partner', partner, 'updated')
        self.assertEqual(len(first), 1, 'the first change did not notify')

        # A distinct write_date is what separates the two events; without it
        # both collapse onto the same key.
        partner.write({'name': 'Shifting Ltd B', 'write_date': '2030-01-01 00:00:00'})
        second = Message._trigger_event('res.partner', partner, 'updated')
        self.assertEqual(len(second), 1, 'the second change was swallowed as a duplicate')
        self.assertNotEqual(first.idempotency_key, second.idempotency_key)

    def test_the_same_change_is_still_deduped(self):
        """Replaying one event must stay idempotent - that is the whole point
        of the key, and base.automation can fire twice in one transaction."""
        Message = self.env['midvex.notification.message']
        partner = self.env['res.partner'].create({'name': 'Steady Ltd'})
        partner.write({'name': 'Steady Ltd A'})
        first = Message._trigger_event('res.partner', partner, 'updated')
        again = Message._trigger_event('res.partner', partner, 'updated')
        self.assertEqual(len(first), 1)
        self.assertEqual(len(again), 0)


class TestRecipientLanguage(TransactionCase):
    """Template subjects and bodies are translatable, but the environment doing
    the rendering belongs to whoever saved the record. Rendered there, a
    Turkish colleague's alert arrives in English purely because an
    English-speaking user happened to trigger it."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.adapter = MockAdapter()
        registry._ADAPTERS[cls.adapter.channel_code] = cls.adapter
        cls.channel = ensure_channel(cls.env, cls.adapter.channel_code, 'Mock Channel')
        cls.account = cls.env['midvex.notification.account'].create({
            'name': 'Language account', 'channel_id': cls.channel.id, 'state': 'connected',
        })
        # Activated, not installed: activating is enough to store a translation
        # against the language, and installing one would pull the whole
        # catalogue into every run of this suite.
        cls.env['res.lang']._activate_lang('tr_TR')

        cls.english = cls.env['res.users'].create({
            'name': 'English Member', 'login': 'notif_lang_en',
            'email': 'en@example.com', 'lang': 'en_US',
        })
        cls.turkish = cls.env['res.users'].create({
            'name': 'Turkish Member', 'login': 'notif_lang_tr',
            'email': 'tr@example.com', 'lang': 'tr_TR',
        })
        for user in (cls.english, cls.turkish):
            cls.env['midvex.notification.recipient'].create({
                'user_id': user.id, 'account_id': cls.account.id,
                'state': 'linked', 'external_id': 'chat-%s' % user.id,
            })
        cls.room = cls.env['midvex.notification.recipient'].create({
            'kind': 'group', 'name': 'Shared room', 'account_id': cls.account.id,
            'state': 'linked', 'external_id': '-100777',
        })

        partner_model = cls.env['ir.model']._get('res.partner')
        cls.template = cls.env['midvex.notification.template'].create({
            'name': 'Partner created', 'code': 'lang_partner_created',
            'model_id': partner_model.id, 'subject': 'New partner',
            'body': '{{ object.name }} was created',
        })
        cls.template.with_context(lang='tr_TR').write({
            'subject': 'Yeni cari', 'body': '{{ object.name }} oluşturuldu',
        })
        cls.rule = cls.env['midvex.notification.rule'].create({
            'name': 'Notify both languages', 'model_id': partner_model.id,
            'trigger': 'on_create', 'template_id': cls.template.id,
            'channel_ids': [(4, cls.channel.id)],
            'audience_user_ids': [(4, cls.english.id), (4, cls.turkish.id)],
            'audience_recipient_ids': [(4, cls.room.id)],
        })

    @classmethod
    def tearDownClass(cls):
        registry.unregister_adapter(cls.adapter.channel_code)
        super().tearDownClass()

    def test_one_event_renders_per_recipient_language(self):
        partner = self.env['res.partner'].create({'name': 'Acme Corp'})
        created = self.env['midvex.notification.message']._trigger_event(
            'res.partner', partner, 'created')

        by_user = {message.recipient_id.user_id: message for message in created}
        self.assertEqual(by_user[self.english].body, 'Acme Corp was created')
        self.assertEqual(by_user[self.english].subject, 'New partner')
        self.assertEqual(by_user[self.turkish].body, 'Acme Corp oluşturuldu')
        self.assertEqual(by_user[self.turkish].subject, 'Yeni cari')

    def test_a_group_chat_keeps_the_acting_language(self):
        """A shared chat has no user to ask - the kind constraint forbids one -
        so it falls back rather than picking somebody's language at random."""
        partner = self.env['res.partner'].create({'name': 'Beta Corp'})
        created = self.env['midvex.notification.message']._trigger_event(
            'res.partner', partner, 'created')

        room_message = created.filtered(lambda message: message.recipient_id == self.room)
        self.assertEqual(len(room_message), 1)
        self.assertEqual(room_message.body, 'Beta Corp was created')


class TestQueueIsWokenOnEnqueue(TransactionCase):
    """Nothing sends at enqueue time, so without a trigger the cron's own
    interval is the entire delivery latency."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.adapter = MockAdapter()
        registry._ADAPTERS[cls.adapter.channel_code] = cls.adapter
        cls.channel = ensure_channel(cls.env, cls.adapter.channel_code, 'Mock Channel')
        cls.account = cls.env['midvex.notification.account'].create({
            'name': 'Trigger account', 'channel_id': cls.channel.id, 'state': 'connected',
        })
        cls.member = cls.env['res.users'].create({
            'name': 'Trigger Member', 'login': 'notif_trigger_member',
            'email': 'trigger@example.com',
        })
        cls.env['midvex.notification.recipient'].create({
            'user_id': cls.member.id, 'account_id': cls.account.id,
            'state': 'linked', 'external_id': 'chat-trigger',
        })
        partner_model = cls.env['ir.model']._get('res.partner')
        cls.template = cls.env['midvex.notification.template'].create({
            'name': 'Partner created', 'code': 'trigger_partner_created',
            'model_id': partner_model.id, 'body': '{{ object.name }} was created',
        })
        cls.rule = cls.env['midvex.notification.rule'].create({
            'name': 'Notify on creation', 'model_id': partner_model.id, 'trigger': 'on_create',
            'template_id': cls.template.id, 'channel_ids': [(4, cls.channel.id)],
            'audience_user_ids': [(4, cls.member.id)],
        })
        cls.cron = cls.env.ref(
            'midvex_o_notification_foundry.ir_cron_notification_process_pending')

    @classmethod
    def tearDownClass(cls):
        registry.unregister_adapter(cls.adapter.channel_code)
        super().tearDownClass()

    def _triggers(self):
        return self.env['ir.cron.trigger'].search_count([('cron_id', '=', self.cron.id)])

    def test_enqueueing_wakes_the_queue(self):
        before = self._triggers()
        partner = self.env['res.partner'].create({'name': 'Prompt Ltd'})
        created = self.env['midvex.notification.message']._trigger_event(
            'res.partner', partner, 'created')

        self.assertEqual(len(created), 1)
        self.assertGreater(self._triggers(), before, 'the queue cron was never woken')

    def test_an_event_that_enqueues_nothing_does_not_wake_the_queue(self):
        """The rule matches, but the message is already queued - waking the
        cron for a dedupe would have it scan for nothing."""
        partner = self.env['res.partner'].create({'name': 'Repeat Ltd'})
        self.env['midvex.notification.message']._trigger_event('res.partner', partner, 'created')
        before = self._triggers()

        again = self.env['midvex.notification.message']._trigger_event(
            'res.partner', partner, 'created')

        self.assertEqual(len(again), 0)
        self.assertEqual(self._triggers(), before)
