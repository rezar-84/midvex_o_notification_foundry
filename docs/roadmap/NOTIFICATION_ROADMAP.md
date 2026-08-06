# Notification Roadmap

## Phase 1 — Foundry MVP

- channel registry;
- account configuration;
- recipient linking;
- message templates;
- notification rules;
- delivery queue;
- delivery logs;
- retry policy;
- dashboard skeleton;
- dummy channel adapter tests.

## Phase 2 — Telegram MVP

- verify Bot API docs;
- implement adapter (`send`, `test_connection`, `register_webhook`, `parse_error`);
- implement webhook controller and secret-token verification;
- implement `/link` recipient linking;
- wire the first rule: "CRM lead created" → Telegram;
- stabilize foundry.

## Phase 3 — Foundry hardening

- dashboard polish (stat buttons, filters);
- error grouping;
- job batching;
- improved rule/audience UI;
- idempotency improvements;
- log redaction review.

## Phase 4 — Email MVP

- reuse Odoo's `mail.mail`/`ir.mail_server` where possible;
- implement channel adapter;
- reuse foundry flows;
- add tests.

## Phase 5 — Slack MVP

- verify current Slack API/webhook style;
- implement channel adapter;
- reuse foundry flows;
- add tests.

## Phase 6 — WhatsApp / SMS MVP

- verify official WhatsApp Business / SMS provider APIs;
- implement channel adapter(s);
- reuse foundry flows;
- add tests.

## Phase 7 — Advanced operations

- richer templates (attachments, rich formatting per channel);
- delivery analytics/reporting dashboard;
- per-user channel preference center;
- escalation/SLA rules;
- additional trigger events beyond lead creation (stage changes, task assignment, low stock, etc.).
