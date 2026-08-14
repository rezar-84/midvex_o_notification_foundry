"""Sanitized WhatsApp Cloud API payloads.

Shapes taken from Meta's published webhook payload examples, verified
2026-08-14 — see docs/projects/notification_whatsapp/API_RESEARCH.md. Every
identifier, phone number, name and message body has been replaced.

Inline Python rather than JSON files on disk: the existing suite has no
fixture-loading helper, and adding one for six payloads would be more machinery
than it saves. It also keeps the secret scan trivially able to see them.
"""

WABA_ID = '100000000000001'
PHONE_NUMBER_ID = '200000000000002'
DISPLAY_PHONE_NUMBER = '905000000000'
CUSTOMER_WA_ID = '905111111111'

INBOUND_WAMID = 'wamid.TEST0000000000000000000000000000INBOUND'
OUTBOUND_WAMID = 'wamid.TEST000000000000000000000000000OUTBOUND'


def _envelope(value):
    return {
        'object': 'whatsapp_business_account',
        'entry': [{'id': WABA_ID, 'changes': [{'value': value, 'field': 'messages'}]}],
    }


def _value(**extra):
    value = {
        'messaging_product': 'whatsapp',
        'metadata': {
            'display_phone_number': DISPLAY_PHONE_NUMBER,
            'phone_number_id': PHONE_NUMBER_ID,
        },
    }
    value.update(extra)
    return value


def inbound_text(body='Do you ship to Izmir?', wamid=INBOUND_WAMID):
    return _envelope(_value(
        contacts=[{'profile': {'name': 'Test Customer'}, 'wa_id': CUSTOMER_WA_ID}],
        messages=[{
            'from': CUSTOMER_WA_ID,
            'id': wamid,
            'timestamp': '1749416383',
            'type': 'text',
            'text': {'body': body},
        }],
    ))


def inbound_unsupported(message_type='sticker'):
    """A type the adapter does not read.

    It must still produce an event with an identity, so it is stored and
    deduped rather than silently dropped — and above all must not crash the
    handler.
    """
    return _envelope(_value(
        contacts=[{'profile': {'name': 'Test Customer'}, 'wa_id': CUSTOMER_WA_ID}],
        messages=[{
            'from': CUSTOMER_WA_ID,
            'id': INBOUND_WAMID,
            'timestamp': '1749416383',
            'type': message_type,
            message_type: {'id': 'media-id-placeholder'},
        }],
    ))


def status(state='delivered', wamid=OUTBOUND_WAMID, errors=None):
    entry = {
        'id': wamid,
        'status': state,
        'timestamp': '1750263773',
        'recipient_id': CUSTOMER_WA_ID,
        'conversation': {'id': 'conversation-placeholder', 'origin': {'type': 'service'}},
        'pricing': {'billable': True, 'pricing_model': 'CBP', 'category': 'service'},
    }
    if errors:
        entry['errors'] = errors
    return _envelope(_value(statuses=[entry]))


def status_failed(wamid=OUTBOUND_WAMID):
    return status('failed', wamid, errors=[{
        'code': 131026,
        'title': 'Message undeliverable',
        'error_data': {'details': 'Receiver is incapable of receiving this message.'},
    }])


def two_messages_one_notification():
    """One notification carrying two messages.

    Meta batches. An adapter that returned only the first event would lose the
    second silently, which is why parse_inbound returns a list.
    """
    return _envelope(_value(
        contacts=[{'profile': {'name': 'Test Customer'}, 'wa_id': CUSTOMER_WA_ID}],
        messages=[
            {'from': CUSTOMER_WA_ID, 'id': INBOUND_WAMID + 'A', 'timestamp': '1749416383',
             'type': 'text', 'text': {'body': 'First'}},
            {'from': CUSTOMER_WA_ID, 'id': INBOUND_WAMID + 'B', 'timestamp': '1749416384',
             'type': 'text', 'text': {'body': 'Second'}},
        ],
    ))


def send_success(wamid=OUTBOUND_WAMID):
    return {
        'messaging_product': 'whatsapp',
        'contacts': [{'input': '+%s' % CUSTOMER_WA_ID, 'wa_id': CUSTOMER_WA_ID}],
        'messages': [{'id': wamid}],
    }


def error_body(code, details='Something went wrong.', subcode=None):
    payload = {
        'message': 'Unsupported post request.',
        'type': 'OAuthException',
        'code': code,
        'error_data': {'messaging_product': 'whatsapp', 'details': details},
        'fbtrace_id': 'trace-placeholder',
    }
    if subcode is not None:
        payload['error_subcode'] = subcode
    return {'error': payload}
