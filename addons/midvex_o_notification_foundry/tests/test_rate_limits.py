from datetime import timedelta

from odoo import fields
from odoo.exceptions import UserError
from odoo.tests.common import TransactionCase

from ..services import registry
from .common import ensure_channel


class ThrottledAdapter:
    """A channel with tight, easily-provoked limits.

    The real numbers are Telegram's (1/second per chat, 20/minute per group);
    the group figure is kept small here so a test does not have to enqueue
    twenty-one messages to reach it.
    """
    channel_code = 'notification_throttled'
    rate_limit_chat_seconds = 1
    rate_limit_group_per_minute = 2
    rate_limit_global_per_second = 30

    def __init__(self):
        self.send_calls = []
        self.failure = None

    def test_connection(self, account):
        return {'ok': True}

    def send(self, account, message_dto):
        if self.failure:
            raise self.failure
        self.send_calls.append(message_dto)
        return {'ok': True, 'provider_message_id': 'thr-%s' % len(self.send_calls)}

    def register_webhook(self, account, webhook_url, secret_token):
        return {'ok': True}

    def parse_inbound(self, raw_payload):
        return {}

    def parse_error(self, response_or_exception):
        return {
            'error_code': 'THROTTLED_ERROR',
            'message': str(response_or_exception),
            'retryable': getattr(response_or_exception, 'is_retryable', True),
            'retry_after_seconds': getattr(response_or_exception, 'retry_after', None),
        }


class RateLimitCase(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.adapter = ThrottledAdapter()
        registry._ADAPTERS[cls.adapter.channel_code] = cls.adapter
        cls.channel = ensure_channel(cls.env, cls.adapter.channel_code, 'Throttled Channel')
        cls.account = cls.env['midvex.notification.account'].create({
            'name': 'Throttled account', 'channel_id': cls.channel.id, 'state': 'connected',
        })
        cls.user = cls.env['res.users'].create({
            'name': 'Throttle Member', 'login': 'notif_throttle_member',
            'email': 'throttle@example.com',
        })
        cls.person = cls.env['midvex.notification.recipient'].create({
            'user_id': cls.user.id, 'account_id': cls.account.id,
            'state': 'linked', 'external_id': 'chat-person',
        })
        cls.room = cls.env['midvex.notification.recipient'].create({
            'kind': 'group', 'name': 'Busy room', 'account_id': cls.account.id,
            'state': 'linked', 'external_id': '-100555',
        })
        cls.Message = cls.env['midvex.notification.message']

    @classmethod
    def tearDownClass(cls):
        registry.unregister_adapter(cls.adapter.channel_code)
        super().tearDownClass()

    def setUp(self):
        super().setUp()
        # The adapter is a plain Python object created once per class, so
        # nothing rolls its call log back between tests the way the database
        # is rolled back.
        self.adapter.send_calls = []
        self.adapter.failure = None

    def _message(self, recipient, key):
        return self.Message.create({
            'recipient_id': recipient.id, 'account_id': self.account.id,
            'body': 'body %s' % key, 'idempotency_key': key,
        })


class TestThrottling(RateLimitCase):
    """Sending is what consumes a channel's allowance, so the check has to run
    per message immediately before the send - never once for the batch."""

    def test_a_second_message_to_one_chat_is_deferred(self):
        first = self._message(self.person, 'chat-1')
        second = self._message(self.person, 'chat-2')

        self.Message.cron_process_pending()

        self.assertEqual(first.state, 'sent')
        self.assertEqual(second.state, 'pending')
        self.assertEqual(second.hold_reason, 'rate_limit')
        self.assertTrue(second.hold_until)
        self.assertEqual(len(self.adapter.send_calls), 1)

    def test_the_deferred_message_goes_out_once_the_window_passes(self):
        first = self._message(self.person, 'chat-1')
        second = self._message(self.person, 'chat-2')
        self.Message.cron_process_pending()
        self.assertEqual(second.state, 'pending')

        # Age the send out of the one-second window rather than sleeping.
        first.sent_at = fields.Datetime.now() - timedelta(seconds=30)
        second.hold_until = False
        self.Message.cron_process_pending()

        self.assertEqual(second.state, 'sent')
        self.assertFalse(second.hold_reason)

    def test_a_group_gets_its_own_per_minute_ceiling(self):
        """A person's chat and a room have different limits, and the room's is
        the one a busy rule breaches first."""
        messages = [self._message(self.room, 'room-%s' % index) for index in range(3)]

        for _run in messages:
            # Age each send past the one-second per-chat window and release the
            # hold it caused, so the only limit still in play is the group's
            # per-minute ceiling - which nothing here ages past.
            for message in messages:
                if message.sent_at:
                    message.sent_at = fields.Datetime.now() - timedelta(seconds=5)
                if message.state == 'pending':
                    message.hold_until = False
            self.Message.cron_process_pending()

        sent = [message for message in messages if message.state == 'sent']
        held = [message for message in messages if message.state == 'pending']
        self.assertEqual(len(sent), 2, 'the group ceiling of 2/minute was not applied')
        self.assertEqual(len(held), 1)
        self.assertEqual(held[0].hold_reason, 'rate_limit')

    def test_a_throttled_chat_does_not_starve_the_rest_of_the_batch(self):
        """The whole point of deferring rather than sleeping: one busy room
        must not hold up everybody else's alerts."""
        self._message(self.room, 'room-a')
        self.Message.cron_process_pending()

        blocked = self._message(self.room, 'room-b')
        free = self._message(self.person, 'person-a')
        self.Message.cron_process_pending()

        self.assertEqual(blocked.state, 'pending')
        self.assertEqual(blocked.hold_reason, 'rate_limit')
        self.assertEqual(free.state, 'sent', 'an unrelated chat was blocked behind a busy one')

    def test_quiet_hours_and_rate_limits_are_told_apart(self):
        """Both hold a message; only one of them means somebody should look at
        the rule's audience."""
        message = self._message(self.person, 'quiet-1')
        now = fields.Datetime.now()
        # A window built around the real clock, per the handoff log's warning
        # about tests that only pass at certain times of day.
        self.person.write({
            'quiet_enabled': True,
            'quiet_start': (now.hour - 1) % 24 + now.minute / 60.0,
            'quiet_end': (now.hour + 1) % 24 + now.minute / 60.0,
            'tz': 'UTC',
        })

        self.Message.cron_process_pending()

        self.assertEqual(message.state, 'pending')
        self.assertEqual(message.hold_reason, 'quiet_hours')


class TestFailureHandling(RateLimitCase):
    """parse_error and its retryable/retry_after_seconds keys were in the
    adapter contract from the start and nothing called them."""

    def test_a_rate_limit_does_not_consume_an_attempt(self):
        """Three 429s used to mark a perfectly good message permanently failed,
        and a 429 says nothing at all about the message."""
        message = self._message(self.person, 'fail-429')
        failure = UserError('Too Many Requests')
        failure.retry_after = 42
        self.adapter.failure = failure
        self.addCleanup(setattr, self.adapter, 'failure', None)

        before = fields.Datetime.now()
        message.action_process()

        self.assertEqual(message.state, 'pending')
        self.assertEqual(message.attempt_count, 0, 'the rate limit burned an attempt')
        self.assertEqual(message.error_code, 'THROTTLED_ERROR')
        self.assertGreaterEqual(message.next_retry_at, before + timedelta(seconds=41))
        self.assertLessEqual(message.next_retry_at, before + timedelta(seconds=60))

    def test_repeated_rate_limits_never_exhaust_the_message(self):
        message = self._message(self.person, 'fail-429-loop')
        failure = UserError('Too Many Requests')
        failure.retry_after = 1
        self.adapter.failure = failure
        self.addCleanup(setattr, self.adapter, 'failure', None)

        for _unused in range(5):
            message.write({'state': 'pending', 'next_retry_at': False})
            message.action_process()

        self.assertEqual(message.state, 'pending')
        self.assertEqual(message.attempt_count, 0)

    def test_a_permanent_error_is_quarantined_rather_than_retried(self):
        message = self._message(self.person, 'fail-permanent')
        failure = UserError('Bad Request: chat not found')
        failure.is_retryable = False
        self.adapter.failure = failure
        self.addCleanup(setattr, self.adapter, 'failure', None)

        message.action_process()

        self.assertEqual(message.state, 'quarantined')
        self.assertFalse(message.next_retry_at)

    def test_generic_failures_back_off_instead_of_repeating_a_flat_delay(self):
        message = self._message(self.person, 'fail-generic')
        self.adapter.failure = UserError('Service Unavailable')
        self.addCleanup(setattr, self.adapter, 'failure', None)

        delays = []
        for _unused in range(2):
            before = fields.Datetime.now()
            message.write({'state': 'pending'})
            message.action_process()
            delays.append(round((message.next_retry_at - before).total_seconds() / 60))

        self.assertEqual(message.state, 'pending')
        self.assertEqual(delays, [1, 5], 'the backoff did not grow between attempts')

        message.write({'state': 'pending'})
        message.action_process()
        self.assertEqual(message.state, 'failed', 'max_attempts stopped being enforced')


class TestDestinationAddressedMessages(RateLimitCase):
    """Messages addressed to a raw destination rather than a staff recipient.

    ADR-020 made recipient_id optional so conversation replies can share this
    one queue. Everything below is the queue continuing to behave — the point
    is that it does, for a row shaped differently from every row it saw before.
    """

    def _to(self, destination, key):
        return self.Message.create({
            'destination_external_id': destination, 'account_id': self.account.id,
            'body': 'body %s' % key, 'idempotency_key': key,
        })

    def test_a_message_needs_a_recipient_or_a_destination(self):
        """Dropping required=True must not allow a message addressed to nobody."""
        from odoo.exceptions import ValidationError
        with self.assertRaises(ValidationError):
            self.Message.create({
                'account_id': self.account.id, 'body': 'nowhere',
                'idempotency_key': 'no-destination',
            })

    def test_a_recipient_whose_address_is_unknown_still_queues(self):
        """Addressed to somebody we cannot yet reach is not addressed to nobody.

        A recipient who has not finished linking has no external_id. Refusing
        the message at create sounds stricter and is worse: the failure then
        has no row, no log and nothing in the queue for anyone to find. It
        queues, and the adapter says why at send.
        """
        unlinked = self.env['midvex.notification.recipient'].create({
            'kind': 'group', 'name': 'Not yet linked', 'account_id': self.account.id,
            'state': 'pending',
        })
        message = self.Message.create({
            'recipient_id': unlinked.id, 'account_id': self.account.id,
            'body': 'queued anyway', 'idempotency_key': 'dest-unlinked',
        })
        self.assertTrue(message.id)
        self.assertFalse(message.sudo().destination_key)

    def test_the_destination_reaches_the_adapter(self):
        message = self._to('+905111111111', 'dest-1')
        message.action_process()
        self.assertEqual(message.state, 'sent')
        self.assertEqual(self.adapter.send_calls[0]['recipient_external_id'], '+905111111111')

    def test_a_recipient_still_wins_when_both_are_present(self):
        """The recipient is the richer record; the raw field is the fallback."""
        message = self.Message.create({
            'recipient_id': self.person.id, 'destination_external_id': 'ignored',
            'account_id': self.account.id, 'body': 'both', 'idempotency_key': 'dest-both',
        })
        self.assertEqual(message.sudo().destination_key, 'chat-person')

    def test_two_destinations_do_not_throttle_each_other(self):
        """The bug this keying change exists to prevent.

        Keyed on recipient_id, every conversation reply would have shared one
        empty recordset as its key — so one customer's message would have paced
        every other customer's. Two different numbers must both go out.
        """
        first = self._to('+905111111111', 'dest-a')
        second = self._to('+905222222222', 'dest-b')

        self.Message.cron_process_pending()

        self.assertEqual(first.state, 'sent')
        self.assertEqual(second.state, 'sent')
        self.assertEqual(len(self.adapter.send_calls), 2)

    def test_one_destination_still_throttles_itself(self):
        first = self._to('+905111111111', 'dest-c')
        second = self._to('+905111111111', 'dest-d')

        self.Message.cron_process_pending()

        self.assertEqual(first.state, 'sent')
        self.assertEqual(second.state, 'pending')
        self.assertEqual(second.hold_reason, 'rate_limit')

    def test_a_destination_and_a_recipient_sharing_an_address_throttle_together(self):
        """Because the provider sees one chat, whatever Odoo calls it.

        This is the correction hiding inside the keying change: the limit was
        always per destination, and recipient_id was a proxy that happened to
        work while every message had one.
        """
        recipient_message = self._message(self.person, 'dest-e')
        destination_message = self._to('chat-person', 'dest-f')

        self.Message.cron_process_pending()

        self.assertEqual(recipient_message.state, 'sent')
        self.assertEqual(destination_message.state, 'pending')
        self.assertEqual(destination_message.hold_reason, 'rate_limit')

    def test_quiet_hours_are_skipped_rather_than_crashing(self):
        """_quiet_release_at calls ensure_one().

        Asked of a message with no recipient it would raise inside the cron and
        take the whole batch with it — every other pending message in that run,
        for reasons having nothing to do with any of them.
        """
        message = self._to('+905111111111', 'dest-quiet')
        self.Message.cron_process_pending()
        self.assertEqual(message.state, 'sent')

    def test_the_same_address_on_another_account_is_a_different_destination(self):
        """Two companies' numbers are throttled by two different providers."""
        other_account = self.env['midvex.notification.account'].create({
            'name': 'Second throttled account', 'channel_id': self.channel.id,
            'state': 'connected',
        })
        first = self._to('+905111111111', 'dest-g')
        second = self.Message.create({
            'destination_external_id': '+905111111111', 'account_id': other_account.id,
            'body': 'other account', 'idempotency_key': 'dest-h',
        })

        self.Message.cron_process_pending()

        self.assertEqual(first.state, 'sent')
        self.assertEqual(second.state, 'sent')
