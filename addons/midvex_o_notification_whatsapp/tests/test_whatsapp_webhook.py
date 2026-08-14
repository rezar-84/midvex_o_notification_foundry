import hashlib
import hmac
import json

from odoo.tests.common import TransactionCase

from . import fixtures
from ..controllers.whatsapp_webhook import constant_time_equals, signature_is_valid
from ..models.whatsapp_inbound_event import NotificationInboundEvent

APP_SECRET = 'app-secret-placeholder'


def sign(body, secret=APP_SECRET):
    return 'sha256=' + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


class TestWhatsAppSignature(TransactionCase):
    """Signature verification, tested on the function rather than over HTTP.

    The routing layer adds nothing to this decision, and testing the predicate
    directly lets every mutation be tried cheaply.
    """

    def setUp(self):
        super().setUp()
        self.body = json.dumps(fixtures.inbound_text()).encode()

    def test_a_correct_signature_is_accepted(self):
        self.assertTrue(signature_is_valid(sign(self.body), self.body, APP_SECRET))

    def test_a_forged_signature_is_rejected(self):
        forged = 'sha256=' + '0' * 64
        self.assertFalse(signature_is_valid(forged, self.body, APP_SECRET))

    def test_a_signature_from_another_secret_is_rejected(self):
        self.assertFalse(signature_is_valid(sign(self.body, 'other-secret'),
                                             self.body, APP_SECRET))

    def test_a_body_altered_after_signing_is_rejected(self):
        signature = sign(self.body)
        tampered = self.body.replace(b'Izmir', b'Ankara')
        self.assertNotEqual(tampered, self.body)
        self.assertFalse(signature_is_valid(signature, tampered, APP_SECRET))

    def test_reserialized_json_does_not_verify(self):
        """The signature covers bytes, not meaning.

        Verifying against json.dumps(parsed) instead of the raw body is the
        obvious mistake here, and it fails silently in the safe direction until
        a payload's key order or spacing differs — at which point every genuine
        webhook is rejected.
        """
        signature = sign(self.body)
        reserialized = json.dumps(json.loads(self.body.decode()), indent=2).encode()
        self.assertFalse(signature_is_valid(signature, reserialized, APP_SECRET))

    def test_a_missing_header_is_rejected(self):
        self.assertFalse(signature_is_valid(None, self.body, APP_SECRET))
        self.assertFalse(signature_is_valid('', self.body, APP_SECRET))

    def test_a_header_without_the_algorithm_prefix_is_rejected(self):
        bare = hmac.new(APP_SECRET.encode(), self.body, hashlib.sha256).hexdigest()
        self.assertFalse(signature_is_valid(bare, self.body, APP_SECRET))

    def test_a_non_ascii_signature_header_is_rejected_not_crashed(self):
        """This endpoint is reachable by anyone who finds the URL.

        hmac.compare_digest raises TypeError on a str carrying any non-ASCII
        character, so passing an attacker-controlled header straight to it
        turns a 403 into a 500 — and Meta retries a 500 while it does not retry
        a 403. One high byte would have made the endpoint noisily retryable by
        a stranger.
        """
        for header in ('sha256=ürk', 'sha256=' + 'ÿ' * 64, 'sha256=🙂'):
            with self.subTest(header=header):
                self.assertFalse(signature_is_valid(header, self.body, APP_SECRET))

    def test_a_non_ascii_secret_does_not_crash_verification(self):
        """The secret is typed into a form by a person, so it can be anything."""
        secret = 'gizli-anahtar-şifre'
        self.assertTrue(signature_is_valid(sign(self.body, secret), self.body, secret))
        self.assertFalse(signature_is_valid(sign(self.body, 'other'), self.body, secret))

    def test_verification_fails_closed_when_no_secret_is_configured(self):
        """Unlike the Telegram webhook, which fails open for a staff linking bot.

        An unverified WhatsApp payload can create records on behalf of a
        customer. There is no version of accepting that by default which is
        safe, so an unconfigured account rejects everything rather than
        accepting everything.
        """
        self.assertFalse(signature_is_valid(sign(self.body), self.body, None))
        self.assertFalse(signature_is_valid(sign(self.body), self.body, ''))


class TestConstantTimeEquals(TransactionCase):
    """Used by both the signature check and the GET verify-token check."""

    def test_equal_values_match(self):
        self.assertTrue(constant_time_equals('abc', 'abc'))
        self.assertTrue(constant_time_equals('şifre', 'şifre'))

    def test_different_values_do_not(self):
        self.assertFalse(constant_time_equals('abc', 'abd'))
        self.assertFalse(constant_time_equals('şifre', 'sifre'))

    def test_none_never_matches(self):
        """A missing hub.verify_token must be a refusal, not a comparison."""
        self.assertFalse(constant_time_equals(None, 'abc'))
        self.assertFalse(constant_time_equals('abc', None))
        self.assertFalse(constant_time_equals(None, None))

    def test_mixed_str_and_bytes_are_comparable(self):
        self.assertTrue(constant_time_equals('abc', b'abc'))


class TestWhatsAppEventKey(TransactionCase):
    """The dedupe key, which decides what counts as the same event twice."""

    def test_a_message_keys_on_its_wamid(self):
        key = NotificationInboundEvent.build_wa_event_key(
            {'event_type': 'message', 'external_message_id': 'wamid.A'})
        self.assertEqual(key, 'msg:wamid.A')

    def test_a_status_keys_on_wamid_and_state(self):
        """One message produces sent, delivered and read — all naming one wamid.

        Keying on the wamid alone would let the first status arrive and silently
        reject the other two, leaving every message stuck at 'sent'.
        """
        keys = {
            NotificationInboundEvent.build_wa_event_key(
                {'event_type': 'status', 'external_message_id': 'wamid.A', 'status': state})
            for state in ('sent', 'delivered', 'read')
        }
        self.assertEqual(len(keys), 3)

    def test_a_redelivered_status_produces_the_same_key(self):
        event = {'event_type': 'status', 'external_message_id': 'wamid.A', 'status': 'read'}
        self.assertEqual(NotificationInboundEvent.build_wa_event_key(event),
                         NotificationInboundEvent.build_wa_event_key(dict(event)))

    def test_an_event_without_an_id_has_no_key(self):
        """Stored unconditionally rather than dropped.

        Keeping a possible duplicate of an unidentifiable payload beats losing
        it: the row is the evidence an operator needs when a customer says they
        messaged and nobody replied.
        """
        self.assertIsNone(NotificationInboundEvent.build_wa_event_key(
            {'event_type': 'message'}))


class TestWhatsAppInboundEventModel(TransactionCase):
    """The constraint that makes dedupe hold under a race, not only under a search."""

    def setUp(self):
        super().setUp()
        from odoo.addons.midvex_o_notification_foundry.tests.common import ensure_channel
        self.channel = ensure_channel(self.env, 'whatsapp', 'WhatsApp')
        self.account = self.env['midvex.notification.account'].create({
            'name': 'Test WhatsApp',
            'channel_id': self.channel.id,
            'wa_phone_number_id': fixtures.PHONE_NUMBER_ID,
        })
        self.Inbound = self.env['midvex.notification.inbound.event']

    def _create(self, key):
        return self.Inbound.create({
            'channel_id': self.channel.id,
            'account_id': self.account.id,
            'event_type': 'message',
            'wa_event_key': key,
        })

    def test_the_same_key_cannot_be_stored_twice(self):
        from psycopg2 import IntegrityError
        self._create('msg:wamid.A')
        with self.assertRaises(IntegrityError), self.env.cr.savepoint():
            self._create('msg:wamid.A')

    def test_different_keys_coexist(self):
        self._create('msg:wamid.A')
        self._create('msg:wamid.B')
        self.assertEqual(self.Inbound.search_count([('account_id', '=', self.account.id)]), 2)

    def test_events_without_a_key_are_not_constrained(self):
        """Telegram's rows leave this NULL, and Postgres treats NULLs as distinct.

        Without that, installing this module would make the Telegram webhook
        reject the second message anyone ever sent the bot.
        """
        self._create(None)
        self._create(None)
        self.assertEqual(self.Inbound.search_count([('account_id', '=', self.account.id)]), 2)

    def test_the_same_key_on_another_account_is_a_different_event(self):
        other = self.env['midvex.notification.account'].create({
            'name': 'Second WhatsApp',
            'channel_id': self.channel.id,
            'wa_phone_number_id': '300000000000003',
        })
        self._create('msg:wamid.A')
        self.Inbound.create({
            'channel_id': self.channel.id, 'account_id': other.id,
            'event_type': 'message', 'wa_event_key': 'msg:wamid.A',
        })
        self.assertEqual(self.Inbound.search_count([('wa_event_key', '=', 'msg:wamid.A')]), 2)


class TestWhatsAppDeliveryStatus(TransactionCase):
    """The status ladder, exercised on the controller's own helper.

    Driven directly rather than over HTTP: routing adds nothing to the decision,
    and out-of-order arrival is easier to provoke by calling in the wrong order
    than by constructing six signed requests.
    """

    def setUp(self):
        super().setUp()
        from odoo.addons.midvex_o_notification_foundry.tests.common import ensure_channel
        from ..controllers.whatsapp_webhook import WhatsAppWebhookController

        self.controller = WhatsAppWebhookController
        channel = ensure_channel(self.env, 'whatsapp', 'WhatsApp')
        self.account = self.env['midvex.notification.account'].create({
            'name': 'Test WhatsApp', 'channel_id': channel.id,
            'wa_phone_number_id': fixtures.PHONE_NUMBER_ID,
        })
        self.recipient = self.env['midvex.notification.recipient'].create({
            'kind': 'user', 'user_id': self.env.user.id, 'account_id': self.account.id,
            'external_id': '+%s' % fixtures.CUSTOMER_WA_ID, 'state': 'linked',
        })
        self.message = self.env['midvex.notification.message'].create({
            'name': 'Test', 'recipient_id': self.recipient.id, 'account_id': self.account.id,
            'body': 'Hello', 'idempotency_key': 'wa-test-1', 'state': 'sent',
            'result': {'provider_message_id': fixtures.OUTBOUND_WAMID},
        })

    def advance(self, status):
        self.controller._record_delivery_state(self.message, status)

    def test_the_wamid_is_derived_from_the_delivery_result(self):
        """Which is what lets the webhook find this row in one indexed query.

        Deriving it means the foundry's send path stays untouched — it knows
        nothing about wamids and should not have to.
        """
        self.assertEqual(self.message.wa_message_id, fixtures.OUTBOUND_WAMID)

    def test_the_ladder_advances(self):
        self.advance('sent')
        self.assertEqual(self.message.wa_delivery_status, 'sent')
        self.advance('delivered')
        self.assertEqual(self.message.wa_delivery_status, 'delivered')
        self.advance('read')
        self.assertEqual(self.message.wa_delivery_status, 'read')

    def test_read_arriving_before_delivered_is_not_undone(self):
        """The ordinary case, not an edge case.

        Meta does not guarantee ordering and routinely delivers `read` first.
        Writing whatever arrived last would show a message the customer has
        read as merely delivered.
        """
        self.advance('read')
        self.advance('delivered')
        self.assertEqual(self.message.wa_delivery_status, 'read')

    def test_a_redelivered_status_is_not_logged_twice(self):
        self.advance('delivered')
        before = self.env['midvex.notification.log'].search_count(
            [('message_id', '=', self.message.id)])
        self.advance('delivered')
        after = self.env['midvex.notification.log'].search_count(
            [('message_id', '=', self.message.id)])
        self.assertEqual(before, after)

    def test_an_unknown_status_changes_nothing(self):
        self.advance('delivered')
        self.advance('something_meta_added_later')
        self.assertEqual(self.message.wa_delivery_status, 'delivered')

    def test_a_message_from_another_channel_gets_no_wamid(self):
        """The compute is scoped by channel.

        A Telegram result also carries a provider_message_id, and copying it
        into a WhatsApp-shaped column would have the webhook match a status
        against a Telegram message.
        """
        from odoo.addons.midvex_o_notification_foundry.tests.common import ensure_channel
        telegram = ensure_channel(self.env, 'telegram', 'Telegram')
        account = self.env['midvex.notification.account'].create({
            'name': 'Telegram account', 'channel_id': telegram.id,
        })
        recipient = self.env['midvex.notification.recipient'].create({
            'kind': 'group', 'name': 'Room', 'account_id': account.id,
            'external_id': '-100', 'state': 'linked',
        })
        message = self.env['midvex.notification.message'].create({
            'name': 'Test', 'recipient_id': recipient.id, 'account_id': account.id,
            'body': 'Hello', 'idempotency_key': 'tg-test-1', 'state': 'sent',
            'result': {'provider_message_id': 42},
        })
        self.assertFalse(message.wa_message_id)


class TestWhatsAppAccountValidation(TransactionCase):
    def setUp(self):
        super().setUp()
        from odoo.addons.midvex_o_notification_foundry.tests.common import ensure_channel
        self.channel = ensure_channel(self.env, 'whatsapp', 'WhatsApp')

    def test_a_whatsapp_account_needs_a_phone_number_id(self):
        """Caught at save, not at send.

        Missing configuration that only fails when a real alert goes out is the
        same class of mistake as the live account whose channel code was '1':
        silent until it is a customer who did not hear back.
        """
        from odoo.exceptions import ValidationError
        with self.assertRaises(ValidationError):
            self.env['midvex.notification.account'].create({
                'name': 'Unconfigured', 'channel_id': self.channel.id,
            })

    def test_other_channels_are_unaffected(self):
        from odoo.addons.midvex_o_notification_foundry.tests.common import ensure_channel
        telegram = ensure_channel(self.env, 'telegram', 'Telegram')
        account = self.env['midvex.notification.account'].create({
            'name': 'Telegram account', 'channel_id': telegram.id,
        })
        self.assertTrue(account.id)
