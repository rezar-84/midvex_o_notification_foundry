# Implementation Plan — Notification Foundry

## Milestone 1 — Documentation and source verification

- Create project docs.
- Confirm local environment guide.
- Verify the Telegram Bot API against official docs before implementation.

## Milestone 2 — Module skeleton

Create `midvex_o_notification_foundry` with manifest, security, menus, empty models, and tests.

## Milestone 3 — Channel registry

Implement `midvex.notification.channel`, the adapter registry, and a dummy test adapter.

## Milestone 4 — Account management

Implement the notification account model, company-scoped configuration, channel selection, credential fields with masking, and test-connection delegation.

## Milestone 5 — Recipient linking

Implement the recipient model, link-code generation, and the "My Notification Settings" self-service view (no channel API calls yet — pure Odoo).

## Milestone 6 — Templates

Implement the template model and rendering via Odoo's `mail.render.mixin`.

## Milestone 7 — Rules and dispatch

Implement the rule model, the generic `base.automation` event-wiring pattern, and `services/dispatcher.py::enqueue_event`.

## Milestone 8 — Delivery queue and logs

Implement the message queue model, cron runner (`process_pending`), retry policy, and structured logs.

## Milestone 9 — Dashboard and UX

Implement the accounts/rules/templates/queue/logs/recipients dashboard and menus.

## Milestone 10 — Telegram MVP integration

Build the Telegram channel module to validate foundry assumptions end to end.

## Milestone 11 — Webhook + linking end-to-end

Wire the Telegram webhook controller, `/link` flow, and the first "CRM lead created" rule together; confirm delivery.

## Milestone 12 — Refactor and stabilize

Move reusable logic discovered while building Telegram into the foundry before adding Email, Slack, or WhatsApp.
