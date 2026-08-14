from odoo.exceptions import UserError
from odoo.addons.midvex_o_notification_foundry.services.registry import register_adapter

from .whatsapp_client import (
    AUTHENTICATION_CODES,
    PERMISSION_CODES,
    POLICY_RESTRICTED_CODES,
    RATE_LIMIT_CODES,
    RECIPIENT_INVALID_CODES,
    TEMPLATE_INVALID_CODES,
    WhatsAppClient,
    WhatsAppError,
)


@register_adapter
class WhatsAppAdapter:
    channel_code = 'whatsapp'

    # Meta's published limits, verified 2026-08-14 — see
    # docs/projects/notification_whatsapp/API_RESEARCH.md. They live here rather
    # than in the foundry because the foundry must not know anything
    # channel-specific, and because the numbers belong next to the research
    # that justifies them.
    #
    # The per-recipient figure is the one that bites: six seconds between
    # messages to one person is slow enough that a rule matching several
    # records for the same customer will hit it from a single batch. Bursts of
    # up to 45 in six seconds are tolerated and then repaid, so treating the
    # sustained rate as the limit is the conservative reading.
    rate_limit_chat_seconds = 6         # one message per six seconds to one recipient
    rate_limit_global_per_second = 80   # eighty per second per business number

    #: Meta documents no Retry-After on Cloud API rate limits, so when one
    #: arrives without a hint we wait a fixed interval rather than hammering.
    #: Long enough to clear a per-recipient window several times over, short
    #: enough that a transient throughput limit does not delay an alert by
    #: minutes.
    default_retry_after_seconds = 30

    def __init__(self):
        self.client = WhatsAppClient()

    # --- connection ----------------------------------------------------

    def test_connection(self, account):
        result = self.client.get_phone_number(account)
        if not result.get('id'):
            raise UserError('WhatsApp did not return a phone number id for this account.')
        # action_test_connection looks for 'username' or 'name' to display.
        # verified_name is the business name Meta shows to customers, which is
        # the most useful thing to confirm back to whoever pressed the button.
        return {
            'name': result.get('verified_name') or result.get('display_phone_number'),
            'display_phone_number': result.get('display_phone_number'),
            'quality_rating': result.get('quality_rating'),
            'id': result.get('id'),
        }

    # --- sending -------------------------------------------------------

    def send(self, account, message_dto):
        recipient = message_dto.get('recipient_external_id')
        if not recipient:
            raise WhatsAppError('Recipient has no linked WhatsApp phone number.',
                                permanent=True)

        payload = self._build_payload(account, recipient, message_dto)
        result = self.client.send_message(account, payload)

        messages = result.get('messages') or []
        provider_message_id = messages[0].get('id') if messages else None
        if not provider_message_id:
            # A 200 with no wamid means the message was not accepted, whatever
            # the status line said. Treating it as sent would leave a message
            # marked delivered that no status webhook will ever mention again.
            raise UserError('WhatsApp accepted the request but returned no message id.')

        # 'submitted', not 'sent': the API acknowledging the request only means
        # Meta has it. The message model's terminal state is 'sent', so that is
        # what goes back — but the real ladder is carried on the webhook, which
        # is where sent/delivered/read actually arrive.
        return {'provider_message_id': provider_message_id, 'status': 'sent', 'raw': result}

    def _build_payload(self, account, recipient, message_dto):
        """A text message, or a template when one is mapped for this account.

        Business-initiated messages outside the 24-hour customer service window
        must be approved templates; the provider rejects free text with error
        131047. The foundry has no idea whether a window is open — it has no
        conversation model yet — so the rule here is the conservative one: if a
        template mapping exists for this notification template, use it.
        """
        template = self._resolve_template(account, message_dto)
        if template:
            return {
                'messaging_product': 'whatsapp',
                'recipient_type': 'individual',
                'to': recipient,
                'type': 'template',
                'template': template,
            }
        return {
            'messaging_product': 'whatsapp',
            'recipient_type': 'individual',
            'to': recipient,
            'type': 'text',
            'text': {'preview_url': False, 'body': message_dto.get('body') or ''},
        }

    def _resolve_template(self, account, message_dto):
        template_code = message_dto.get('template_code')
        if not template_code:
            return None
        mapping = account.env['midvex.notification.whatsapp.template'].sudo().find_for(
            account, template_code, self._recipient_lang(account, message_dto))
        if not mapping:
            return None
        return mapping.build_component_payload(message_dto)

    @staticmethod
    def _recipient_lang(account, message_dto):
        """The language the body was rendered in.

        enqueue_event already renders each message in the recipient's own
        language (ADR-011), so the mapping must be looked up in that same
        language or a Turkish body would be sent under an English template
        header. The message DTO does not carry the language, so it is read back
        off the recipient the same way the render did.
        """
        message = account.env['midvex.notification.message'].sudo().browse(
            message_dto.get('message_id') or 0)
        user = message.recipient_id.user_id if message.exists() else False
        return (user.lang if user else False) or account.env.lang or 'en_US'

    # --- webhook -------------------------------------------------------

    def register_webhook(self, account, webhook_url, secret_token):
        """Not an API call for WhatsApp.

        Telegram registers its callback URL over the API with setWebhook. Meta
        does not: the callback URL and verify token are configured in the App
        Dashboard, against the app rather than the phone number, and there is no
        endpoint that sets them.

        Raising rather than silently succeeding matters — action_register_webhook
        is a button, and a button that reports success while doing nothing is
        how someone concludes the webhook is wired when it is not.
        """
        raise UserError(
            'WhatsApp callback URLs are configured in the Meta App Dashboard, not over '
            'the API. Set the Callback URL and Verify Token there against the app, using '
            'the URL and token from this account, then subscribe the WhatsApp Business '
            'Account to the "messages" field.')

    def parse_inbound(self, raw_payload):
        """Flatten one Cloud API webhook body into events.

        Returns a list, unlike Telegram's single-event parse: one notification
        can carry several messages and several statuses, and dropping all but
        the first would silently lose deliveries. Callers that expect one event
        should look at the first element rather than the list.

        Message and status notifications both arrive under field "messages", so
        the branch is on which key is present in the value, not on the field
        name.
        """
        events = []
        for entry in raw_payload.get('entry') or []:
            waba_id = entry.get('id')
            for change in entry.get('changes') or []:
                value = change.get('value') or {}
                metadata = value.get('metadata') or {}
                common = {
                    'waba_id': waba_id,
                    'phone_number_id': metadata.get('phone_number_id'),
                    'display_phone_number': metadata.get('display_phone_number'),
                    'raw': raw_payload,
                }
                contacts = {
                    contact.get('wa_id'): (contact.get('profile') or {}).get('name')
                    for contact in value.get('contacts') or []
                }
                for message in value.get('messages') or []:
                    events.append(dict(common, **self._inbound_message(message, contacts)))
                for status in value.get('statuses') or []:
                    events.append(dict(common, **self._inbound_status(status)))
        return events

    @staticmethod
    def _inbound_message(message, contacts):
        sender = message.get('from')
        message_type = message.get('type') or 'unknown'
        # Only text is read. Every other type still produces an event with an
        # external id, so it is stored and deduped rather than dropped — an
        # unsupported sticker must not crash the handler or, worse, be
        # acknowledged and forgotten.
        body = (message.get('text') or {}).get('body') if message_type == 'text' else None
        return {
            'event_type': 'message',
            'external_id': message.get('id'),
            'external_message_id': message.get('id'),
            'sender_identifier': sender,
            'external_username': contacts.get(sender),
            'message_type': message_type,
            'text': body,
            'timestamp': message.get('timestamp'),
            'supported': message_type == 'text',
        }

    @staticmethod
    def _inbound_status(status):
        return {
            'event_type': 'status',
            # The wamid of the message being reported on, which is what links
            # this back to a queued row. Not a new identifier of its own.
            'external_id': status.get('id'),
            'external_message_id': status.get('id'),
            'status': status.get('status'),
            'recipient_identifier': status.get('recipient_id'),
            'timestamp': status.get('timestamp'),
            'errors': status.get('errors') or [],
        }

    # --- error classification ------------------------------------------

    def parse_error(self, response_or_exception):
        """Normalize a failure into the adapter contract's error shape.

        Classification is by Meta's numeric code, not by matching its wording.
        The Telegram adapter matches strings because the Bot API returns prose;
        the Cloud API returns a number, and using it means a reworded message
        cannot silently reclassify a permanent failure as a retryable one.
        """
        message = str(response_or_exception)
        code = getattr(response_or_exception, 'code', None)
        status = getattr(response_or_exception, 'http_status', None)

        if getattr(response_or_exception, 'permanent', False):
            # Raised before the request went out — no token, no phone number ID,
            # no recipient. The record is wrong, not the network, and three
            # attempts spread over half an hour would only delay somebody
            # noticing.
            return {'error_code': 'WHATSAPP_NOT_CONFIGURED', 'message': message,
                    'retryable': False, 'retry_after_seconds': None}

        if code in RATE_LIMIT_CODES or status == 429:
            retry_after = getattr(response_or_exception, 'retry_after', None)
            return {'error_code': 'WHATSAPP_RATE_LIMIT', 'message': message,
                    'retryable': True,
                    'retry_after_seconds': retry_after or self.default_retry_after_seconds}

        for codes, error_code in (
            (AUTHENTICATION_CODES, 'WHATSAPP_AUTH'),
            (PERMISSION_CODES, 'WHATSAPP_PERMISSION'),
            (RECIPIENT_INVALID_CODES, 'WHATSAPP_RECIPIENT_INVALID'),
            (TEMPLATE_INVALID_CODES, 'WHATSAPP_TEMPLATE_INVALID'),
            (POLICY_RESTRICTED_CODES, 'WHATSAPP_POLICY_RESTRICTED'),
        ):
            if code in codes:
                return {'error_code': error_code, 'message': message,
                        'retryable': False, 'retry_after_seconds': None}

        # Everything else retries, including an unrecognised 4xx. Guessing
        # "retryable" wrongly costs two extra attempts; guessing "permanent"
        # wrongly drops a real alert on the floor. New permanent codes belong
        # in the frozensets in whatsapp_client.py as they are found — the
        # published list is longer than the ones handled here, and the rest are
        # rare enough that a retry is the cheaper default.
        return {'error_code': 'WHATSAPP_ERROR', 'message': message,
                'retryable': True, 'retry_after_seconds': None,
                'http_status': status,
                'fbtrace_id': getattr(response_or_exception, 'fbtrace_id', None)}

    # --- conversation contract additions -------------------------------
    # Optional under ADR-015; implemented here because WhatsApp is the channel
    # that needs them first.

    def verify_webhook(self, signature_header, raw_body, app_secret):
        """Delegated to the controller, which holds the raw request body.

        Kept on the adapter so the contract is honoured and a future
        conversation controller has one place to call. See
        controllers/whatsapp_webhook.py for the implementation.
        """
        from ..controllers.whatsapp_webhook import signature_is_valid
        return signature_is_valid(signature_header, raw_body, app_secret)

    @staticmethod
    def normalize_identity(raw_identifier):
        """Canonical E.164 for matching.

        The Cloud API returns wa_id without a leading plus ("16505551234") and
        accepts either form on send. Storing both shapes for one person would
        produce two identities for one customer, so everything is normalized to
        the plussed form on the way in.

        Deliberately not a full phone-number parse: this strips formatting and
        prefixes a plus, and does not attempt to infer a country code from a
        national number. A number without a country code cannot be made
        canonical by guessing, and guessing wrongly maps a customer onto a
        stranger.
        """
        if not raw_identifier:
            return None
        digits = ''.join(character for character in str(raw_identifier) if character.isdigit())
        return '+%s' % digits if digits else None

    def capabilities(self, account=None):
        return {
            'supports_text': True,
            'supports_templates': True,
            'supports_media': False,       # roadmap phase 11
            'supports_read_receipts': True,
            'supports_typing': False,
            'supports_interactive': False,  # roadmap phase 12
            'supports_replies': True,
        }
