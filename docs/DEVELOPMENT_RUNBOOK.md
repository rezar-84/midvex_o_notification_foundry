# Development and Validation Runbook

1. Work only in this monorepo; expose each addon to Odoo with a direct symlink in `/home/rubuntu/Development/odoo19-dev/custom-addons/`.
2. From `/home/rubuntu/Development/odoo19-dev`, load `.agent.env` without printing it and activate `.venv`.
3. Before validation, run the local helper script at `scripts/odoo-dev.sh status` (the `odoo-dev` alias may be absent in non-interactive shells).
4. Install or upgrade with the exact commands in the local environment `AGENTS.md`, using `--stop-after-init`.
5. Run module-tagged tests in an isolated test database. Never use production credentials or a production database.
6. Record command, result, Odoo log evidence, and next action in `docs/HANDOFF_LOG.md`.
