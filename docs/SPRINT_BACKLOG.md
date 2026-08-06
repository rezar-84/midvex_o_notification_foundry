# Sprint Backlog

## Sprint 0 — Governance and environment

- [x] Review product, architecture, security, and Odoo environment guidance.
- [x] Record decisions, risks, handoff process, and test runbook.
- [x] Verify Odoo service and PostgreSQL from the developer shell.

## Sprint 1 — Foundry + Telegram MVP

- [x] Install and upgrade foundry and Telegram modules in `odoo19_dev`.
- [x] Configure a company-scoped Telegram account and test connection (`getMe`) — done 2026-08-03, see `docs/HANDOFF_LOG.md`.
- [ ] Link a test user's Telegram account via the `/link <code>` flow — blocked on a public webhook URL/tunnel (the single remaining prerequisite) plus re-supply of the bot token, see `docs/HANDOFF_LOG.md`.
- [ ] Trigger a `crm.lead` creation and confirm a Telegram message is delivered — blocked on the same tunnel; the enqueue→dispatch→log path is covered by a mocked adapter test in the meantime.
- [x] Demonstrate retry, redacted logs, and idempotent delivery (no duplicate sends on repeated triggers) — covered by mocked dispatch tests (`test_notification_dispatch.py`).
- [x] Complete a fresh-database Odoo test run for both modules — 0 failed, 0 error(s) of 15 tests.

## Sprint 2 — Email MVP

- [ ] Verify requirements against Odoo's own `mail.mail`/`ir.mail_server` before implementation.
- [ ] Implement `midvex_o_notification_email` adapter.
- [ ] Register the Email channel and pass mocked adapter unit tests.
