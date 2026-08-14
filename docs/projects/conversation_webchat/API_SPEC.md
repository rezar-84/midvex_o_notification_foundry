# API Spec — Website Live Chat (customer surface)

## Provenance

The customer-facing half of `varsco_omnichannel_messaging_project/09_LIVE_CHAT_SPEC.md` and `10_FRONTEND_API_SPEC.md`. The agent-facing half and the shared API rules live in `../messaging_api/API_SPEC.md`.

## Principle

The frontend communicates only with Odoo-owned APIs. No Meta, Telegram or other provider secret ever reaches browser code.

## Customer chat endpoints

```text
POST /api/v1/chat/sessions
GET  /api/v1/chat/sessions/{public_id}
GET  /api/v1/chat/sessions/{public_id}/messages
POST /api/v1/chat/sessions/{public_id}/messages
POST /api/v1/chat/sessions/{public_id}/identify
POST /api/v1/chat/sessions/{public_id}/continue-on-whatsapp
```

Capabilities behind them:

- create session;
- identify visitor;
- send message;
- fetch authorized history;
- subscribe to realtime updates;
- close session;
- request WhatsApp continuation.

## Public identifier policy

`{public_id}` is a UUID or opaque token. It is never a database ID, and never enough to enumerate conversations. Possession of it authorizes exactly one session and nothing adjacent to it.

## Response envelope

```json
{
  "data": {
    "id": "public-or-authorized-id",
    "status": "open",
    "channel": "webchat"
  },
  "meta": {
    "correlation_id": "..."
  }
}
```

## Error envelope

```json
{
  "error": {
    "code": "conversation_not_found",
    "message": "Conversation is unavailable."
  },
  "meta": {
    "correlation_id": "..."
  }
}
```

A session that exists but is not yours and a session that does not exist must return the **same** error. Distinguishing them is an enumeration oracle.

## Rules

- explicit versioning;
- JSON schema validation;
- safe error envelope;
- correlation ID on every response;
- no stack traces;
- no secrets;
- server-side company resolution;
- pagination;
- rate limits;
- authorization at controller **and** model levels;
- CSRF/auth strategy appropriate to route type.

## Rate limiting

Per session and per source, at session creation and at message send. Message length capped server-side. Rich content escaped; no arbitrary HTML rendered, ever — the messages come from strangers.
