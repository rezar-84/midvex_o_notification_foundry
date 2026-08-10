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

## ADR-010: Scheduled rules reuse `base.automation`'s `on_time`, and own their automation

### Status

Accepted — 2026-08-10

### Decision

`midvex.notification.rule.trigger` gains `on_schedule`, backed by a `base.automation` whose trigger is `on_time` — Odoo's existing time-based machinery — rather than a cron of our own. The rule carries `date_field_id`, `schedule_offset` and `schedule_offset_mode`, which map onto `trg_date_id`, `trg_date_range` and `trg_date_range_mode`; `trigger_domain` is copied to the automation's `filter_domain` so the scan is filtered in SQL.

Unlike create/update rules, **each scheduled rule owns its automation** rather than sharing one per (model, trigger), and its server action passes `rule_id` so only that rule is dispatched.

A scheduled notification fires **once per record, ever**: the idempotency occurrence is the constant `-sched` rather than `write_date`.

### Reason

`_cron_process_time_based_actions` already fires each record once as its date crosses the window between `last_run` and now, applies the domain in its search, and tunes its own cron interval. Writing a second scanner would duplicate exactly the queue/retry plumbing this project forbids duplicating.

Sharing is impossible here because the watched date, the offset and the domain all live *on* the automation — "due in 3 days" and "overdue by 1" cannot be described by one record. And without `rule_id` in the call, either automation firing would enqueue both rules for any invoice both domains match, so every invoice would be called overdue three days early.

Once-per-record matches `base.automation`'s own semantics and gives a second, independent guard against a reset `last_run`: the first is stamping `last_run = now` when the automation is created, without which enabling a rule would treat every invoice overdue since 1970 as newly due and enqueue the lot.

## ADR-011: Notifications render in the recipient's language

### Status

Accepted — 2026-08-10

### Decision

`enqueue_event` renders each message through `template.with_context(lang=recipient.user_id.lang)`. Group chats have no user, so they keep the acting environment's language.

### Reason

Template subjects and bodies are `translate=True`, but the environment doing the rendering belongs to whoever saved the record. Rendered there, a Turkish recipient received English purely because an English-speaking colleague happened to trigger the alert — which made the Turkish catalogue decorative for exactly the mixed-language teams that need it. The render call already sat inside the per-recipient loop, so this costs no extra renders.

## ADR-012: Delivery is prompt via a cron trigger, and rate limits defer rather than block

### Status

Accepted — 2026-08-10

### Decision

`enqueue_event` calls `ir.cron._trigger()` on the queue cron whenever it creates messages. The periodic five-minute cron stays, as the safety net for retries and quiet-hours releases rather than as the delivery path. Sending is never done inside the transaction that created the message.

Channels declare their own rate limits as adapter attributes. A message that would breach one is stamped with `hold_until`/`hold_reason = 'rate_limit'` and skipped, and the queue is re-triggered for the moment the window opens. The check runs per message immediately before its send, never once per batch.

A 429 returns the attempt it was charged and waits for the channel's own `retry_after`; causes no retry can fix are quarantined; everything else backs off 1, 5, then 25 minutes.

### Reason

Nothing sent at enqueue time, so the cron's interval *was* the delivery latency — an invoice posted at 10:00:01 alerted at 10:05. Measured after the change: **~2 seconds** from commit to the cron processing the message.

Sending synchronously would have been faster still and was rejected: the user's save would then wait on an HTTP call to a third party, and a Telegram outage would make posting an invoice slow or fail. `_trigger()` fires after commit, so the channel can never affect the transaction that produced the alert.

The per-message throttle check is not an optimisation detail: sending is what consumes the allowance, so a batch of twenty-five to one group would all see an empty window and go out together if it were checked once per batch. Deferring rather than sleeping keeps one busy room from starving every other recipient, and avoids holding the only cron worker doing nothing.

Not counting a 429 against `max_attempts` is the point of the failure rework. Being rate-limited says nothing about the message, and three of them used to mark a good alert permanently failed.
