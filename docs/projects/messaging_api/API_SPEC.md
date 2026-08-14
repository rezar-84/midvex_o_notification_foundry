# API Spec — Headless Messaging API

## Provenance

Merged from `varsco_omnichannel_messaging_project/10_FRONTEND_API_SPEC.md`, with "Next.js" corrected to "the frontend" (ADR-016). The customer-chat half is duplicated in `../conversation_webchat/API_SPEC.md` for readers arriving from that direction; this file is the whole surface.

## Module

```text
varsco_messaging_api
```

**Planned. Not started.** Roadmap phase 5.

## Principle

The frontend communicates only with Odoo-owned APIs.

Never expose Meta, Telegram, or provider secrets to browser code.

## API ownership

Do not overload `varsco_content_api` indefinitely.

Preferred path:
- keep the existing public content API stable;
- create `varsco_messaging_api`;
- generalize later into `midvex_o_messaging_api` if a second tenant needs it.

`varsco_content_api` is the precedent to copy, not the place to extend: it already establishes `/api/v1/*` routing, an error envelope, portal session auth, and multi-company lead routing on `POST /api/v1/leads`. Read it before designing anything here.

## API groups

### Customer chat API

- create session;
- identify visitor;
- send message;
- fetch authorized history;
- subscribe to realtime updates;
- close session;
- request WhatsApp continuation.

### Agent API

Only if an agent inbox is built outside Odoo. The Odoo inbox (phase 4) needs none of this.

- list conversations;
- get conversation;
- list messages;
- send message;
- assign;
- transfer;
- mark waiting;
- resolve;
- reopen;
- link/create CRM lead;
- create/open quotation;
- fetch partner summary.

## Proposed endpoints

```text
POST /api/v1/chat/sessions
GET  /api/v1/chat/sessions/{public_id}
GET  /api/v1/chat/sessions/{public_id}/messages
POST /api/v1/chat/sessions/{public_id}/messages

GET  /api/v1/agent/conversations
GET  /api/v1/agent/conversations/{id}
GET  /api/v1/agent/conversations/{id}/messages
POST /api/v1/agent/conversations/{id}/messages
POST /api/v1/agent/conversations/{id}/assign
POST /api/v1/agent/conversations/{id}/resolve
POST /api/v1/agent/conversations/{id}/reopen
POST /api/v1/agent/conversations/{id}/crm
POST /api/v1/agent/conversations/{id}/quotation
```

The two groups have fundamentally different auth models — an anonymous stranger holding an opaque session token, versus an authenticated employee with company scope and record rules. They share a prefix and nothing else. Do not let a helper written for one leak into the other.

## API rules

- explicit versioning;
- JSON schema validation;
- safe error envelope;
- correlation ID;
- no stack traces;
- no secrets;
- server-side company resolution;
- pagination;
- rate limits;
- authorization at controller and model levels;
- CSRF/auth strategy appropriate to route type.

## Public identifier policy

Use UUID/opaque tokens for customer-exposed resources.

Never expose enough information to enumerate conversations.

Note the asymmetry in the endpoint list above: customer routes take `{public_id}`, agent routes take `{id}`. That is deliberate — an authenticated employee reading a database ID is fine, and record rules do the work. A stranger must never see one.

## Response example

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

## Error example

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
