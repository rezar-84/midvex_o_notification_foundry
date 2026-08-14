# Midvex Odoo Notification Foundry

Odoo 19 monorepo for the shared multi-channel notification foundry, its channel
adapters, and — from 2026-08 — the omnichannel conversation suite that sits
beside it.

## Addons

- `addons/midvex_o_notification_foundry` — the engine: adapter registry, delivery
  queue, retry, throttling, delivery logs, templates, rules, security, UI.
- `addons/midvex_o_notification_telegram` — Telegram channel adapter and webhook.
- `addons/midvex_o_notification_business` — business event content: CRM, sales and
  accounting notification templates and rules, with Turkish translations.

## Documentation

- `docs/projects/PROJECT_INDEX_NOTIFICATION.md` — every project and its status.
- `docs/architecture/NOTIFICATION_SUITE_ARCHITECTURE.md` — the notification half.
- `docs/projects/omnichannel_messaging/` — the conversation half: WhatsApp, live
  chat, unified inbox, CRM bridge, AI. Documented; mostly not yet built.
- `docs/projects/notification_foundry/DECISIONS.md` — ADR-001 onward.

## Working here

For local Odoo discovery, create direct symlinks from the authoritative
`custom-addons` directory to each addon. Follow `AGENTS.md` and
`docs/DEVELOPMENT_RUNBOOK.md`; never place bot tokens, webhook secrets, or
other channel credentials in the repository.
