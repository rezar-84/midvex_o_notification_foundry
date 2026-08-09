# Sprint Backlog

## Sprint 0 — Governance and environment

- [x] Review product, architecture, security, and Odoo environment guidance.
- [x] Record decisions, risks, handoff process, and test runbook.
- [x] Verify Odoo service and PostgreSQL from the developer shell.

## Sprint 1 — Foundry + Telegram MVP

- [x] Install and upgrade foundry and Telegram modules in `odoo19_dev`.
- [x] Configure a company-scoped Telegram account and test connection (`getMe`) — done 2026-08-03, see `docs/HANDOFF_LOG.md`.
- [x] Link a test user's Telegram account via the `/link <code>` flow — done 2026-08-08 against `erp.varsco.com`. The tunnel prerequisite fell away rather than being met: production is itself a public HTTPS host, so `setWebhook` and inbound `/link` work there with no tunnel at all.
- [ ] Trigger a `crm.lead` creation and confirm a Telegram message is delivered — no longer blocked on a tunnel. Remaining: deploy the 2026-08-08 commits to erp, repair the live account's channel (its code is `1`, so no adapter resolves and every send fails), and set an audience on the shipped rule, which ships with none.
- [x] Demonstrate retry, redacted logs, and idempotent delivery (no duplicate sends on repeated triggers) — covered by mocked dispatch tests (`test_notification_dispatch.py`).
- [x] Complete a fresh-database Odoo test run for both modules — 0 failed, 0 error(s) of 15 tests (25 as of 2026-08-08).

## Sprint 2 — Beyond the MVP

- [x] Group-chat recipients (feature 7) — a shared chat is its own recipient `kind`, forbidden from carrying a `user_id`, and link codes are refused when redeemed in the wrong kind of chat.
- [x] Quiet hours (half of feature 8) — delivery is held and released, never dropped; windows cross midnight and are read on the recipient's own clock.
- [ ] Digest (the other half of feature 8) — batch a recipient's queued alerts into one message instead of a burst. Not started. Needs a second cron and a way to keep each event's row honest while only one message is delivered.
- [ ] Delivery dashboard (feature 9) — the foundry manifest's summary still advertises a dashboard that does not exist. Either build it or stop claiming it.
- [x] Rules wire their own `base.automation` — until 2026-08-09 a rule added in the UI matched nothing and reported no error.
- [x] Send by hand — the compose wizard, reachable from the menu, a linked recipient, and a record's Actions menu, replacing the Message Queue's dead Create button.
- [x] Ready-made business events — `midvex_o_notification_business` (CRM, Sales, Invoicing).
- [ ] Migrate `template_lead_created` / `rule_lead_created_telegram` out of the Telegram adapter into the business module. They are `noupdate="1"` records already installed on production, so moving the XML ids needs a migration rather than a cut and paste. Left alone deliberately.

## Sprint 3 — Email MVP

- [ ] Verify requirements against Odoo's own `mail.mail`/`ir.mail_server` before implementation.
- [ ] Implement `midvex_o_notification_email` adapter.
- [ ] Register the Email channel and pass mocked adapter unit tests.
