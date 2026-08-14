# PRD — Website Live Chat

## Provenance

Merged from `varsco_omnichannel_messaging_project/09_LIVE_CHAT_SPEC.md`, with "Next.js" corrected to "the frontend" throughout (ADR-016).

## Goal

Provide a branded live chat experience inside the website frontend while Odoo remains the source of truth.

## UX principles

This is B2B sales chat, not anonymous high-volume consumer chat.

Initial pre-chat identity:
- name: required;
- email or WhatsApp: at least one required;
- company: optional;
- country: optional/inferred with confirmation;
- topic: optional but recommended;
- consent/privacy acknowledgement where required.

Do not force a long questionnaire before chat starts.

The existing widget's four quick-topic buttons already do the "topic" half of this well, and in nine languages. Keep them.

## Progressive qualification

After conversation starts, system or AI can request:
- product;
- species;
- quantity;
- destination;
- purchase timeframe;
- business type.

## Session model

Browser receives an opaque short-lived chat/session token.

Token:
- must not expose Odoo IDs directly;
- must be revocable/expiring;
- must only access the associated chat;
- must be rate-limited.

## API flow

```text
POST /chat/sessions
POST /chat/sessions/{public_id}/messages
GET  /chat/sessions/{public_id}/messages
POST /chat/sessions/{public_id}/identify
POST /chat/sessions/{public_id}/continue-on-whatsapp
```

Exact paths follow the conventions already established by `varsco_content_api`'s `/api/v1/*` routes. See `../messaging_api/API_SPEC.md`.

## Realtime

Preferred:
- SSE or WebSocket;
- Odoo bus may be used behind the gateway if reliable in the current deployment.

Fallback:
- bounded long-polling.

Avoid 1–2 second constant polling.

## Agent availability

Frontend may show:
- online;
- offline;
- response expected later.

Do not promise unrealistic response times.

## Web-to-WhatsApp handoff

Customer may explicitly choose to continue on WhatsApp.

System:
1. verifies/collects phone;
2. links WhatsApp identity;
3. uses appropriate approved outbound WhatsApp mechanism;
4. creates WhatsApp session under same conversation thread;
5. preserves CRM linkage.

Step 3 is not optional cleverness: a business-initiated WhatsApp message to someone who has not messaged the number in the last 24 hours **must** be an approved template, or the provider rejects it with error `131047`. The continuation template has to exist and be approved before this feature can ship.

## Abuse prevention

- rate limiting;
- bot/spam controls;
- message length limits;
- token expiry;
- optional CAPTCHA/risk check at session creation;
- server-side validation.
