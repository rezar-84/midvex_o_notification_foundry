# Decisions — Notification Foundry

## ADR-001: Build foundry before channel modules

### Status

Accepted

### Decision

Create `midvex_o_notification_foundry` as the shared engine.

### Reason

It reduces repeated code across Telegram, Email, Slack, and WhatsApp.

## ADR-002: Channel modules are thin adapters

### Status

Accepted

### Decision

Channel modules handle API-specific authentication, payloads, responses, and errors only; they never write foundry records directly outside the DTOs the dispatcher passes them.

## ADR-003: Telegram first

### Status

Accepted

### Decision

Build Telegram as the first real channel implementation, then generalize the foundry.

### Reason

It is the channel the user needs immediately (lead-created alerts to team members) and it exercises both outbound delivery and inbound webhook handling.

## ADR-004: Queue-first delivery

### Status

Accepted

### Decision

Outbound delivery runs through queued `midvex.notification.message` records processed by cron, never synchronously inside the transaction that created the triggering event.

## ADR-005: Reuse Odoo's mail.render.mixin for templates

### Status

Accepted

### Decision

Message templates render through Odoo's own `mail.render.mixin` (the same Jinja-based engine `mail.template` uses) instead of a custom template/variable-substitution engine.

### Reason

It is already tested, already supports safe variable substitution against a record, and avoids maintaining a parallel rendering engine.

## ADR-006: Non-invasive event wiring

### Status

Accepted

### Decision

Event wiring uses a generic `base.automation` + `ir.actions.server` record calling a foundry helper method, never inheriting or monkey-patching target models such as `crm.lead`.

### Reason

Keeps the foundry non-invasive to other Odoo apps and makes adding a new trigger a data change, not a code change.

## ADR-007: Self-service recipient linking

### Status

Accepted

### Decision

Telegram recipient linking uses a self-service `/link <code>` bot command matched against a per-user, short-lived code, instead of manual chat-id entry by an administrator.

### Reason

Scales to any number of members without administrator involvement per user and avoids storing chat ids that were never confirmed by the owning user.

## ADR-008: Telegram webhook mode

### Status

Accepted — 2026-08-01

### Decision

Telegram updates are received via a webhook controller, not long polling, per explicit product decision. The module must install and run cleanly without a public HTTPS URL configured; webhook registration (`setWebhook`) is a manual action, not automatic on install.

### Reason

Webhook delivery is near-instant and matches the user's choice; deferring `setWebhook` to a manual action keeps the module installable in environments (like the current local dev instance) that do not yet have a public URL.

## ADR-009: Concrete event wiring lives in the channel module, not the foundry

### Status

Accepted — 2026-08-01

### Decision

The generic `base.automation`/`ir.actions.server` mechanism and the `_trigger_event` helper live in the foundry (model-agnostic). The concrete "CRM lead created" automation record, plus the demo `notification.rule`/`notification.template` pairing it to the Telegram channel, ship as data in `midvex_o_notification_telegram` instead, which already needs a `crm` dependency for its demo data.

### Reason

The foundry must not depend on `crm` or hard-code any specific business model just to install; only the module demonstrating a concrete integration should carry that dependency and data.
