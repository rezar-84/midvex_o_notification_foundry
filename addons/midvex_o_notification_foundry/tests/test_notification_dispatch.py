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
