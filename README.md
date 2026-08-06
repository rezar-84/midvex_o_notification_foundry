# Midvex Odoo Notification Foundry

Odoo 19 monorepo for the shared multi-channel notification foundry and channel adapters.

## Addons

- `addons/midvex_o_notification_foundry`
- `addons/midvex_o_notification_telegram`

For local Odoo discovery, create direct symlinks from the authoritative
`custom-addons` directory to each addon. Follow `AGENTS.md` and
`docs/DEVELOPMENT_RUNBOOK.md`; never place bot tokens, webhook secrets, or
other channel credentials in the repository.
