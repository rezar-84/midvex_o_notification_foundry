# Architecture — WhatsApp Notification Connector

## Module structure

```text
midvex_o_notification_whatsapp/
├── __init__.py
├── __manifest__.py
├── models/
│   ├── __init__.py
│   ├── whatsapp_account.py          _inherit midvex.notification.account
│   └── whatsapp_template_map.py     midvex.notification.whatsapp.template
├── services/
│   ├── __init__.py
│   ├── whatsapp_client.py           transport — shared (ADR-017)
│   └── whatsapp_adapter.py          channel_code = 'whatsapp'
├── controllers/
│   ├── __init__.py
│   └── whatsapp_webhook.py          verification + signature + statuses
├── data/
│   └── whatsapp_channel.xml
├── security/
│   └── ir.model.access.csv
├── views/
│   └── whatsapp_views.xml
├── i18n/
└── tests/
    ├── __init__.py
    ├── test_whatsapp_adapter.py
    └── test_whatsapp_webhook.py
```

## Client and adapter are separate on purpose

`whatsapp_client.py` knows HTTP: the base URL, the bearer header, request execution, timeouts, and turning a provider error envelope into the foundry's `error_code` / `retryable` / `retry_after_seconds` contract. It knows nothing about Odoo models.

`whatsapp_adapter.py` knows the foundry: it takes an account and a message DTO, asks the client to do the work, and returns a normalized delivery result.

The seam exists because `midvex_o_conversation_whatsapp` will need the client and must not inherit the notification adapter. Thirty error codes mapped to a taxonomy is not something to get right twice. See ADR-017.

## Foundry integration

The adapter implements the same contract every channel implements — `test_connection`, `send`, `register_webhook`, `parse_inbound`, `parse_error` — and registers itself with `@register_adapter` on `channel_code = 'whatsapp'`.

It does not create Odoo records beyond what the dispatcher passes it. It does not queue, retry, throttle, log deliveries or check permissions; the foundry does all of that, for every channel, once.

## Account model

WhatsApp configuration extends the existing `midvex.notification.account` rather than introducing a second account model. The access token reuses the account's `api_key` field, which is already gated behind `group_notification_admin`; the app secret reuses `api_secret`, and the webhook verify token reuses `webhook_secret`.

New fields are WhatsApp-specific identifiers only: WABA ID, phone number ID, display number, API version, and a test-mode flag.

Reusing the credential fields is deliberate. A new secret field means new masking, new ACL rows and a new way to leak; the existing three already have all of that.

## Company resolution

Inbound payloads carry no `to` field. The destination business number arrives as `value.metadata.phone_number_id`, and that — matched against the account — is what resolves the Odoo company. Never infer a company from anything the sender controls.

## Rate limiting

Declared as adapter class attributes, the way Telegram declares its own. WhatsApp's numbers: 80 messages per second per business number, and one message per 6 seconds to the same recipient. The foundry throttles per message immediately before its send, and defers rather than sleeping.

A 429 defers and returns the attempt. It does not count against `max_attempts` — that distinction is ADR-012, learned by marking good Telegram alerts permanently failed three rate limits in a row.

## Status

**In progress.**
