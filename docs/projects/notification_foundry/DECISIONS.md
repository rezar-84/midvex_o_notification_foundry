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

## ADR-013: Conversations get a sibling foundry, not a bigger notification foundry

### Status

Accepted — 2026-08-14

### Decision

Adopt the omnichannel messaging specification pack into this repository under `docs/projects/{omnichannel_messaging,conversation_foundry,conversation_whatsapp,conversation_webchat,conversation_telegram,messaging_api}/`. The repository copy is canonical; the standalone pack at `~/Projects/varsco_omnichannel_messaging_project/` is a historical drop.

Two-way customer conversation gets its own module, `midvex_o_conversation_foundry`, depending on this one. `midvex_o_notification_foundry` keeps the queue, retry, throttle, delivery logs, templates, rules, channel/account registry and recipient linking, and does not gain a thread, a session or a conversation message model.

### Reason

The two look similar and are not. A notification is an event the business chose to emit: it has a rule, a template, a recipient, a delivery attempt and a terminal state. A conversation message is something a stranger sent us: it has a thread, a counterparty identity, an assignment, a read state and no rule at all. `midvex.notification.message` is a queue row that stops mattering once it is `sent`; `midvex.conversation.message` is a durable record that starts mattering then.

Merging them would mean either a queue full of rows that never leave, or a conversation history that gets pruned with the queue. Both are worse than one dependency edge.

The pack arrived unversioned, in one directory, with no history and no backup. Merging it here was the first thing worth doing regardless of what gets built next.

## ADR-014: Conversation models keep the `midvex.` prefix

### Status

Accepted — 2026-08-14

### Decision

The models are `midvex.conversation.thread`, `.session`, `.message`, `.identity`, `.inbound.event`, `.assignment.event` and `.channel.capability` — not the bare `conversation.*` names the source pack proposes.

### Reason

Every model in this repository is `midvex.notification.*`. An unprefixed `conversation.thread` claims a generic name in a shared Odoo registry where `im_livechat`, `mail` and any future third-party addon are neighbours. The prefix costs nine characters and removes a whole class of collision.

## ADR-015: One adapter registry, extended — not a second one

### Status

Accepted — 2026-08-14

### Decision

Conversation channels register through the existing `addons/midvex_o_notification_foundry/services/registry.py`, keyed on the same `channel_code`. The contract stays the five methods `TelegramAdapter` already implements — `test_connection`, `send`, `register_webhook`, `parse_inbound`, `parse_error` — plus three optional additions with conservative defaults: `verify_webhook`, `normalize_identity`, `capabilities`.

The pack's proposed `validate_account`, `send_message` and `normalize_status_event` are dropped as synonyms of methods that exist. The reconciliation table is in `docs/projects/conversation_foundry/ADAPTER_CONTRACT.md`.

### Reason

The pack says it itself: *"do not invent an incompatible registry when reuse is possible."* Two registries keyed on the same `channel_code` would mean two objects claiming to be the WhatsApp adapter, and `available_adapter_codes()` — which drives the channel Code selection field — would show one of them. That field exists because a free-text channel code once produced a channel nothing could send through, and the mismatch only surfaced at delivery time.

Optional-with-defaults rather than required keeps every existing adapter valid without edits.

## ADR-016: The public website is TanStack Start, not Next.js

### Status

Accepted — 2026-08-14

### Decision

The merged docs describe the frontend generically, and where a stack matters they name the real one. `~/Projects/Websites/varsco_com` is TanStack Start + Vite + React on Bun, Radix/shadcn, Vitest and Playwright, deployed via Docker and Cloudflare Wrangler, and Lovable-connected — its own `AGENTS.md` warns that commits sync back to the Lovable editor and history must not be rewritten.

This supersedes the source pack's ADR-006 and its repeated "headless Next.js" framing.

### Reason

There is no Next.js VARS site. The pack's frontend assumption is simply wrong, and it appears in the brief, the live chat spec, the API spec and an ADR — four places where a reader would take it as settled.

The practical consequence is small today and large at phase 5: `src/components/layout/WhatsAppWidget.tsx` already exists as a nine-language `wa.me` deep-link popover that Odoo never sees. It is the shell to absorb, and the Lovable constraint shapes how anyone may work in that repository.

## ADR-017: WhatsApp is two modules sharing one transport client

### Status

Accepted — 2026-08-14

### Decision

`midvex_o_notification_whatsapp` owns event-driven transactional sending through the foundry queue. `midvex_o_conversation_whatsapp` owns two-way conversation, the customer-service window and identity normalization. Both import one `services/whatsapp_client.py` for auth, base URL, request execution, error parsing and status mapping.

One webhook endpoint per account serves both: `statuses[]` feeds the notification queue, `messages[]` feeds the conversation foundry.

### Reason

Duplicating the HTTP and auth code across two modules is the failure mode the foundry exists to prevent, and error classification in particular is not something to get right twice — the code-to-taxonomy table in `API_RESEARCH.md` has thirty entries and one of them, the rate-limit class, must not consume a retry attempt.

One endpoint rather than two is not a preference: Meta delivers a phone number's callbacks to one URL. Registering a second would silently starve the first.

## ADR-018: Inbound conversational messages are now in scope

### Status

Accepted — 2026-08-14. Supersedes the MVP non-goal in `AGENTS.md`, `docs/projects/notification_foundry/PRD.md` and `docs/projects/notification_telegram/PRD.md`.

### Decision

"Inbound conversational commands beyond `/link`" is no longer a non-goal. Handling inbound customer messages is the point of the conversation foundry.

The non-goal stands for the *notification* modules: `midvex_o_notification_telegram` keeps its six-command staff vocabulary and gains nothing. What changes is that a free-text inbound message stops being stored-and-dropped once `midvex_o_conversation_foundry` exists to receive it.

### Reason

Three documents currently declare this out of scope. Building it while those stand would leave the next reader with a repository whose rules contradict its code, and the rules would lose — quietly, and only for whoever noticed. A scope expansion that is written down is a decision; one that is not is a defect.
