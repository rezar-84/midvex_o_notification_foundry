"""Transport for the WhatsApp Cloud API.

Deliberately separate from the adapter. This module knows HTTP — the base URL,
the bearer header, request execution, and how to turn Meta's error envelope
into something the foundry can classify. It knows nothing about Odoo models.

The seam exists because midvex_o_conversation_whatsapp will need exactly this
and must not inherit the notification adapter to get it. Thirty error codes
mapped onto a taxonomy is not something to get right twice. See ADR-017.

Everything here is verified against
docs/projects/notification_whatsapp/API_RESEARCH.md (checked 2026-08-14).
"""

import json
from urllib import error, parse, request

from odoo.exceptions import UserError

#: Pinned rather than tracking latest. v26.0 shipped 2026-07-29; v25.0 shipped
#: 2026-02-18 and is available until 2028-07-29, which is runway enough. The
#: account carries its own override, so moving is a data change and not a
#: release.
DEFAULT_API_VERSION = 'v25.0'

BASE_URL = 'https://graph.facebook.com'

#: Meta's own numeric codes, grouped by what an operator should do about them.
#: Sources and the full table are in API_RESEARCH.md.
#:
#: Being rate-limited says nothing whatsoever about the message, so those codes
#: are kept strictly apart from failures: the foundry gives back the attempt
#: they were charged. That distinction is ADR-012, and it was learned by
#: marking perfectly good Telegram alerts permanently failed after three 429s.
RATE_LIMIT_CODES = frozenset({
    4,       # app rate limit exceeded
    80007,   # WhatsApp Business Account rate limit reached
    130429,  # Cloud API message throughput limit exceeded
    131048,  # sender phone number has messaging restrictions
    131056,  # too many messages to the same recipient in a short period
    131064,  # messaging limit from template classification violations
    133016,  # registration/deregistration attempt limit exceeded
})

AUTHENTICATION_CODES = frozenset({
    0,    # unable to authenticate app user
    190,  # access token has expired
    200,  # no access token provided
})

PERMISSION_CODES = frozenset({
    3,       # capability or permissions issue
    10,      # permission not granted or removed
    131005,  # permission not granted or removed
})

RECIPIENT_INVALID_CODES = frozenset({
    131021,  # sender and recipient phone number identical
    131026,  # not a WhatsApp user, or otherwise undeliverable
})

TEMPLATE_INVALID_CODES = frozenset({
    132001,  # template missing, or not approved in that language
    132015,  # template paused for low quality
})

#: Restrictions that a retry cannot lift. 131047 in particular is the 24-hour
#: customer service window closing: the fix is an approved template, not
#: another attempt, and retrying only burns the message's remaining tries.
POLICY_RESTRICTED_CODES = frozenset({
    131047,  # more than 24 hours since the recipient last replied
    131049,  # blocked to maintain ecosystem engagement
    131050,  # recipient opted out of marketing messages
})


class WhatsAppError(UserError):
    """A Cloud API failure, carrying enough for the adapter to classify it.

    Subclasses UserError so it surfaces readably from a button press, and
    carries the provider's own fields as attributes rather than only formatted
    into the message — the same trick the Telegram adapter uses for retry_after,
    and for the same reason: parse_error needs real values, not a string to
    parse back apart.
    """

    def __init__(self, message, code=None, subcode=None, http_status=None,
                 fbtrace_id=None, retry_after=None, permanent=False):
        super().__init__(message)
        self.code = code
        self.subcode = subcode
        self.http_status = http_status
        self.fbtrace_id = fbtrace_id
        self.retry_after = retry_after
        # Set for failures raised before the request goes out: a recipient with
        # no phone number, an account with no token. No retry can fix those, and
        # the foundry's default for an unclassified failure is to retry — which
        # would burn all three attempts over half an hour and then report
        # "failed", indistinguishable from a provider outage, when what it
        # actually needs is somebody to fix the record.
        self.permanent = permanent


class WhatsAppClient:
    """Stateless HTTP client. One instance per adapter is fine; it holds nothing."""

    timeout = 20

    def _api_version(self, account):
        return account.wa_api_version or DEFAULT_API_VERSION

    def _token(self, account):
        # sudo() because api_key is gated on group_notification_admin, and the
        # cron user that drains the queue is not an admin. The same pattern the
        # rest of the foundry uses to read account credentials.
        token = account.sudo().api_key
        if not token:
            raise WhatsAppError(
                'WhatsApp access token is not configured on this account.', permanent=True)
        return token

    def _url(self, account, path):
        return f'{BASE_URL}/{self._api_version(account)}/{path}'

    def request(self, account, path, payload=None, method=None):
        """Call the Graph API and return the decoded body.

        Raises WhatsAppError on anything that is not a 2xx, with the provider's
        numeric code attached so parse_error can classify without string
        matching.
        """
        url = self._url(account, path)
        data = json.dumps(payload).encode() if payload is not None else None
        headers = {'Authorization': 'Bearer %s' % self._token(account)}
        if data:
            headers['Content-Type'] = 'application/json'
        req = request.Request(url, data=data, headers=headers, method=method)
        try:
            with request.urlopen(req, timeout=self.timeout) as response:
                return json.loads(response.read().decode() or '{}')
        except error.HTTPError as exc:
            raise self._error_from_http(exc) from exc
        except error.URLError as exc:
            # Never reached Meta, so it says nothing about the message and
            # stays retryable. http_status 0 marks "no response at all",
            # matching what the Telegram adapter does.
            raise WhatsAppError('WhatsApp API connection failed.', http_status=0) from exc

    def _error_from_http(self, exc):
        try:
            body = json.loads(exc.read().decode() or '{}')
        except ValueError:
            body = {}
        payload = body.get('error') or {}
        # error_data.details is the useful half; error.message is often generic.
        details = (payload.get('error_data') or {}).get('details')
        text = details or payload.get('message') or 'HTTP %s' % exc.code
        return WhatsAppError(
            'WhatsApp API request failed: %s' % text,
            code=payload.get('code'),
            subcode=payload.get('error_subcode'),
            http_status=exc.code,
            # Meta support asks for this and nothing else identifies the call.
            fbtrace_id=payload.get('fbtrace_id'),
            retry_after=self._retry_after(exc, payload),
        )

    @staticmethod
    def _retry_after(exc, payload):
        """Seconds to wait, when the provider says so.

        Meta does not document a Retry-After on Cloud API rate limits the way
        Telegram documents retry_after, so the header is read opportunistically
        and a default is supplied by the adapter rather than invented here. A
        wrong number guessed in the transport would be indistinguishable from
        one the provider actually sent.
        """
        header = (exc.headers or {}).get('Retry-After') if hasattr(exc, 'headers') else None
        if header:
            try:
                return int(header)
            except (TypeError, ValueError):
                pass
        return None

    # --- endpoints -----------------------------------------------------

    def get_phone_number(self, account):
        """Read the business phone number node.

        There is no getMe equivalent on the Cloud API. A successful read of the
        phone number node proves the token is valid, the asset assignment is
        right and the phone number id is correct — in one call that messages
        nobody. Sending a real message to test a connection is not an option
        when the recipient is a customer.
        """
        if not account.wa_phone_number_id:
            raise WhatsAppError(
                'WhatsApp phone number ID is not configured on this account.', permanent=True)
        query = parse.urlencode({'fields': 'id,display_phone_number,verified_name,quality_rating'})
        return self.request(account, '%s?%s' % (account.wa_phone_number_id, query))

    def send_message(self, account, payload):
        if not account.wa_phone_number_id:
            raise WhatsAppError(
                'WhatsApp phone number ID is not configured on this account.', permanent=True)
        return self.request(account, '%s/messages' % account.wa_phone_number_id, payload)
