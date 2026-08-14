# Project — WhatsApp Notification Connector

## Module

```text
midvex_o_notification_whatsapp
```

## Depends on

```text
midvex_o_notification_foundry
```

## Purpose

Implement the WhatsApp channel adapter for the notification foundry: event-driven transactional sending, provider template mapping, and delivery results.

**Outbound only.** Two-way customer conversation is a different module with a different owner — see `../conversation_whatsapp/`. The split, and the one transport client they share, is ADR-017.

## Documentation verification

Verified against the official WhatsApp Cloud API documentation on **2026-08-14**. Latest Graph API version is v26.0 (released 2026-07-29); this connector pins **v25.0** as a per-account configuration field. Full details — credentials and scopes, send payloads, webhook verification and signature validation, inbound and status payload shapes, the error code table, rate limits and the 24-hour customer service window — are in `API_RESEARCH.md`.

## MVP scope

- test connection (a `GET` on the phone number node — there is no `getMe` equivalent);
- send a rendered template message (WhatsApp requires pre-approved templates for business-initiated conversations);
- send free-form text inside the 24-hour customer service window;
- semantic template → provider template mapping by company and language;
- error parsing and classification against the provider's numeric codes;
- webhook: verification challenge, signature validation, dedupe, and delivery-status mapping;
- delivery logs, queue, retry and throttling — all inherited from the foundry, none reimplemented.

## Out of scope for this module

- threading inbound customer messages into conversations — `../conversation_whatsapp/`, requires the conversation foundry;
- media messages — roadmap phase 11;
- interactive messages, buttons, location, Flows.

## The webhook is shared

One provider callback URL exists per WhatsApp account, because Meta delivers a phone number's callbacks to exactly one endpoint. This module owns it, and routes `statuses[]` into the notification queue. When the conversation module exists, it will consume the `messages[]` branch of the same endpoint rather than registering a second one.

## Status

**In progress**, roadmap phase 1–2 of `../omnichannel_messaging/ROADMAP.md`, equivalently phase 6 of `docs/roadmap/NOTIFICATION_ROADMAP.md` — the same work, done once.

No Meta credentials are available yet, so everything is built and tested against sanitized fixtures. Live validation is an explicit outstanding step.
