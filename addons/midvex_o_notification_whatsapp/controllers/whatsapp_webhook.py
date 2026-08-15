import hashlib
import hmac
import json
import logging

from psycopg2 import IntegrityError

from odoo import fields
from odoo.http import Controller, request, route

from odoo.addons.midvex_o_notification_foundry.services.registry import get_adapter

_logger = logging.getLogger(__name__)

#: Delivery states, weakest to strongest. Meta does not guarantee ordering and
#: in practice does not deliver it: `read` routinely arrives before `delivered`.
#: Treating arrival order as truth would leave a message that a customer has
#: read sitting at "sent".
_STATUS_RANK = {'sent': 1, 'delivered': 2, 'read': 3}


def constant_time_equals(left, right):
    """hmac.compare_digest over values that may not be ASCII.

    Both callers below compare something a stranger sent against something a
    human typed, and compare_digest raises TypeError on a str containing any
    non-ASCII character. Passed straight through, one high byte in a header
    turns a 403 into a 500 — which is worse than it sounds on this endpoint,
    because Meta retries a 500 and does not retry a 403.

    Encoding both sides sidesteps it: compare_digest on bytes has no such
    restriction, and stays constant-time.
    """
    if left is None or right is None:
        return False
    return hmac.compare_digest(
        left.encode('utf-8', 'surrogatepass') if isinstance(left, str) else left,
        right.encode('utf-8', 'surrogatepass') if isinstance(right, str) else right)


def signature_is_valid(signature_header, raw_body, app_secret):
    """Verify Meta's X-Hub-Signature-256 over the raw request body.

    The signature is an HMAC-SHA256 of the complete, unmodified body keyed with
    the app secret, and the header carries it hex-encoded behind a `sha256=`
    prefix.

    Computing it over re-serialized JSON will never match: json.dumps changes
    whitespace and key order, and the signature covers bytes.

    Returns False when no secret is configured. Unlike the Telegram webhook,
    which fails open in that case for a staff linking bot, this fails closed —
    an unverified WhatsApp payload can create records on behalf of a customer,
    and there is no version of that which is safe by default.
    """
    if not app_secret or not signature_header:
        return False
    if not signature_header.startswith('sha256='):
        return False
    expected = hmac.new(app_secret.encode(), raw_body, hashlib.sha256).hexdigest()
    return constant_time_equals(expected, signature_header[len('sha256='):])


class WhatsAppWebhookController(Controller):

    @route(['/notification/whatsapp/webhook/<int:account_id>'], type='http', auth='public',
           methods=['GET'], csrf=False, save_session=False)
    def whatsapp_verify(self, account_id, **kwargs):
        """Answer Meta's subscription challenge.

        Sent once, when the callback URL is saved in the App Dashboard. Meta
        passes hub.mode=subscribe, a verify token to compare, and an integer
        challenge to echo back verbatim as the body.
        """
        account = self._account(account_id)
        if not account:
            return request.make_response('', status=404)

        mode = kwargs.get('hub.mode')
        token = kwargs.get('hub.verify_token')
        challenge = kwargs.get('hub.challenge')

        expected = account.sudo().webhook_secret
        if mode != 'subscribe' or not expected or not constant_time_equals(token, expected):
            _logger.warning('WhatsApp webhook verification refused for account %s', account_id)
            return request.make_response('', status=403)

        # Echoed as a bare body, not JSON. Meta compares the response text to
        # the challenge it sent and rejects the subscription otherwise.
        return request.make_response(challenge or '', headers=[('Content-Type', 'text/plain')])

    @route(['/notification/whatsapp/webhook/<int:account_id>'], type='http', auth='public',
           methods=['POST'], csrf=False, save_session=False)
    def whatsapp_webhook(self, account_id, **kwargs):
        """Receive a notification: verify, store, dedupe, acknowledge.

        The work done inside this request is deliberately minimal. A slow
        handler makes Meta retry, and a retry that is not deduped duplicates
        whatever the first one created. Status mapping is cheap enough to do
        here; anything heavier belongs in queued work.
        """
        account = self._account(account_id)
        if not account:
            return request.make_response('', status=404)

        # The raw bytes, before any parsing. request.get_json_data() would give
        # a dict that cannot be signed back into the same bytes.
        raw_body = request.httprequest.get_data()
        signature = request.httprequest.headers.get('X-Hub-Signature-256')
        if not signature_is_valid(signature, raw_body, account.sudo().api_secret):
            _logger.warning('WhatsApp webhook signature rejected for account %s', account_id)
            return request.make_json_response({'status': 'forbidden'}, status=403)

        try:
            payload = json.loads(raw_body.decode() or '{}')
        except (ValueError, UnicodeDecodeError):
            # Signed, so it came from Meta, but unreadable. A 400 is honest and
            # will not be retried forever.
            return request.make_json_response({'status': 'error'}, status=400)

        try:
            events = get_adapter('whatsapp').parse_inbound(payload)
        except Exception:
            # A payload shape we cannot parse must still be acknowledged and
            # kept. Returning non-200 would have Meta redeliver something we
            # will fail on identically, forever.
            _logger.exception('WhatsApp webhook could not be parsed for account %s', account_id)
            self._store(account, {'event_type': 'unparsed', 'raw': payload},
                        error_message='Payload could not be parsed.')
            return request.make_json_response({'status': 'ok'}, status=200)

        for event in events:
            self._handle(account, event)

        return request.make_json_response({'status': 'ok'}, status=200)

    # --- helpers -------------------------------------------------------

    @staticmethod
    def _account(account_id):
        account = request.env['midvex.notification.account'].sudo().browse(account_id).exists()
        if not account or account.channel_code != 'whatsapp':
            return None
        return account

    def _handle(self, account, event):
        inbound = self._store(account, event)
        if inbound is None:
            # Already seen. Meta redelivers on any non-200 and occasionally
            # without one, so this is the ordinary path, not an error.
            return
        if event.get('event_type') == 'status':
            self._apply_status(account, event, inbound)

        # The seam the conversation foundry fills in. A no-op without it, so
        # this module installs and runs alone exactly as it did before —
        # customer messages are stored, acknowledged and read by nothing, which
        # is the roadmap's phase-2 behaviour and remains correct on its own.
        #
        # A model hook rather than controller inheritance: controllers are
        # matched by route and the last one loaded wins, which makes the
        # ordering of two modules' routes something you have to reason about.
        # A model method is merged by Odoo the ordinary way and can be extended
        # by any number of channel bridges.
        try:
            inbound.process_conversation_event(account, event)
        except Exception:
            # Threading a message must never make the webhook fail. A non-200
            # has Meta redeliver, and a redelivery of something we already
            # stored is deduped away — so the retry could not fix it and the
            # envelope would be the only record left. It is already stored;
            # this logs loudly and acknowledges.
            _logger.exception(
                'WhatsApp inbound event %s could not be threaded for account %s',
                inbound.id, account.id)
            inbound.write({'error_message': 'Conversation processing failed.'})

    def _store(self, account, event, error_message=False):
        """Record the envelope, or None when it is a duplicate.

        Written before anything is done with the event, so a crash in
        processing still leaves evidence that the event arrived — and so the
        dedupe key is claimed before a concurrent redelivery can claim it.

        Two guards, not one. The search is the fast path and covers the ordinary
        case of Meta redelivering after a timeout. The unique constraint covers
        the race the search cannot: two redeliveries in flight at once, both
        finding nothing. Catching the integrity error inside a savepoint turns
        that race into the same answer the search would have given, instead of
        a 500 and a third redelivery.
        """
        Inbound = request.env['midvex.notification.inbound.event'].sudo()
        key = Inbound.build_wa_event_key(event)
        if key and Inbound.search_count([('account_id', '=', account.id),
                                          ('wa_event_key', '=', key)]):
            return None

        values = {
            'channel_id': account.channel_id.id,
            'account_id': account.id,
            'event_type': event.get('event_type') or 'message',
            'external_id': event.get('external_id'),
            'wa_event_key': key,
            'raw_payload': event.get('raw'),
            'error_message': error_message,
        }
        try:
            with request.env.cr.savepoint():
                return Inbound.create(values)
        except IntegrityError:
            return None

    def _apply_status(self, account, event, inbound):
        """Move a queued message along the delivery ladder.

        Matched on the provider message id stored when the send was accepted.
        A status for a wamid this database never sent is normal — the number
        may be shared with another system, or the row may have been purged — so
        it is stored and dropped rather than treated as an error.
        """
        status = event.get('status')
        wamid = event.get('external_message_id')

        # Marked processed on every path, including the ones that change
        # nothing. "Unprocessed events" is a daily health check in the runbook,
        # and a status about a message this database never sent would otherwise
        # accumulate there as a permanent false alarm.
        inbound.write({'processed': True, 'processed_at': fields.Datetime.now()})

        if not status or not wamid:
            return

        message = request.env['midvex.notification.message'].sudo().search([
            ('account_id', '=', account.id),
            ('wa_message_id', '=', wamid),
        ], limit=1)
        if not message:
            return

        if status == 'failed':
            errors = event.get('errors') or []
            detail = errors[0] if errors else {}
            text = (detail.get('error_data') or {}).get('details') or detail.get('title') \
                or 'WhatsApp reported delivery failure.'
            # Quarantined, not failed: a delivery failure reported after Meta
            # accepted the message is about the recipient, not the transport,
            # and retrying it would send the same message to the same number
            # with the same result.
            message.write({'state': 'quarantined', 'error_message': text,
                           'error_code': 'WHATSAPP_DELIVERY_FAILED'})
            message._log('warning', text, 'WHATSAPP_DELIVERY_FAILED')
            return

        self._record_delivery_state(message, status)

    @staticmethod
    def _record_delivery_state(message, status):
        """Advance the delivery ladder, never moving backwards down it.

        Meta does not guarantee ordering and in practice does not deliver it:
        `read` routinely arrives before `delivered`. Writing whatever arrived
        last would leave a message a customer has read sitting at "delivered",
        or worse, at "sent".

        A repeat of a state already recorded is dropped silently — it is a
        redelivery, and logging it again would fill the delivery log with
        duplicates of good news.
        """
        rank = _STATUS_RANK.get(status)
        if not rank:
            return
        if _STATUS_RANK.get(message.wa_delivery_status, 0) >= rank:
            return
        message.write({'wa_delivery_status': status})
        message._log('success', 'WhatsApp reported the message as %s.' % status,
                     metadata={'delivery_status': status})
