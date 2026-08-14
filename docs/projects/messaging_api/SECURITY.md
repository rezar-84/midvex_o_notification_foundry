# Security — Headless Messaging API

## Provenance

The API-surface slice of `varsco_omnichannel_messaging_project/11_SECURITY_MULTI_COMPANY.md`. The full threat model and multi-company invariants are in `../omnichannel_messaging/SECURITY_MULTI_COMPANY.md`.

## What this surface is exposed to

Everything else in this system is reached by an employee or by a provider whose signature we verify. This one is reached by anyone with a browser. Treat every input as hostile.

## Threats specific to the API

| Threat | Control |
|---|---|
| Conversation enumeration | opaque UUID public IDs; identical error for "not found" and "not yours" |
| Session token theft | short expiry, refresh on activity, individually revocable, stored hashed |
| Cross-company read/write | company resolved server-side from the session, never from a parameter; enforced by record rules, not view domains |
| Spam and abuse | rate limits at session creation and message send, per session and per source; message length capped before parsing |
| Stored XSS | no arbitrary HTML rendered; content escaped on output; rich content sanitized on input |
| Oversized payload | rejected at the controller before JSON parsing |
| Credential exposure | no provider secret exists above the adapter layer; the API layer has none to leak |
| Information disclosure via errors | fixed error envelope, no stack traces, no ORM messages, correlation ID for correlation instead |

## Authorization happens twice

At the controller, and at the model. A controller check alone is one refactor away from being bypassed by a new route; a record rule alone cannot express session-token scope. Both, always.

## The two auth models must not share code

Customer routes authenticate an opaque session token that grants access to exactly one conversation. Agent routes authenticate an Odoo user with company scope, groups and record rules.

A helper that "gets the current conversation" written for the agent side and reused on the customer side is how a stranger ends up reading someone else's thread. Keep them separate even when the code looks duplicated.

## Logging

Log provider, company, account ID, event/message identifiers, status, error code and correlation ID.

Do not log message bodies by default, session tokens ever, or Authorization headers ever. `midvex.notification.log` already redacts metadata keys named `raw`, `body` and `text`; whatever this module logs must be at least as careful.

## Before enabling attachments

MIME validation, size limits, malware scanning, safe filename handling, an Odoo attachment ACL review, and download authorization. Phase 11 — not before, and not "temporarily for testing".
