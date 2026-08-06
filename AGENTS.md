# AGENTS.md — Notification Foundry Project

## Purpose

This file gives AI coding agents the required instructions for building the Odoo 19 multi-channel notification modules.

The agent must use this file together with the local machine guide at:

```text
~/Development/odoo19-dev/AGENTS.md
```

## Mandatory reading order

Before implementation:

1. Read this file.
2. Read `README.md`.
3. Read `docs/architecture/NOTIFICATION_SUITE_ARCHITECTURE.md`.
4. Read `docs/projects/notification_foundry/PRD.md`.
5. Read `docs/projects/notification_foundry/ARCHITECTURE.md`.
6. Read `docs/projects/notification_foundry/DATA_MODEL.md`.
7. Read `docs/projects/notification_foundry/ADAPTER_CONTRACT.md`.
8. Read the target channel docs:
   - `docs/projects/notification_telegram/`
   - `docs/projects/notification_email/`
   - `docs/projects/notification_slack/`
   - `docs/projects/notification_whatsapp/`
9. Read `docs/standards/NOTIFICATION_DEVELOPMENT_STANDARDS.md`.
10. Read `docs/standards/NOTIFICATION_SECURITY.md`.
11. Read the local environment guide at `~/Development/odoo19-dev/AGENTS.md` before running local commands.
12. Read `docs/HANDOFF_LOG.md`, `docs/SPRINT_BACKLOG.md`, and `docs/DEVELOPMENT_RUNBOOK.md` before resuming work.

## Repository and handoff rule

This repository is a monorepo. Addons are stored below `addons/`; Odoo discovers them through direct symlinks in the local `custom-addons/` directory. Do not copy addon files into Odoo core or Enterprise directories.

Before ending a work session, append a handoff entry recording decisions, files changed, commands run, results, open risks, and the exact next validation step. Add architecture/security/product decisions to `docs/projects/notification_foundry/DECISIONS.md`.

## Agent validation rule

Load the local `.agent.env` without printing it. The documented `odoo-dev` command can be an interactive-shell alias, so non-interactive agents should invoke `/home/rubuntu/Development/odoo19-dev/scripts/odoo-dev.sh` or the explicit Python command from the local guide. Always install/upgrade with `--stop-after-init`, then run module-tagged tests in an isolated database.

## Local environment rule

This repository explains what to build.

The local `~/Development/odoo19-dev/AGENTS.md` explains how to run, test, update, and deploy modules on the developer machine.

The agent must not invent local commands, database names, ports, or paths.

## Core project rule

Build the common notification foundry first.

Channel modules must be thin adapters.

Bad:

```text
Telegram module writes its own notification.log/retry/permission logic.
Slack module writes its own notification.log/retry/permission logic.
```

Good:

```text
Channel adapter returns a normalized delivery result.
Foundry logs, retries, and enforces permissions using one shared workflow.
```

## Code ownership

All Odoo modules must be created under the local custom-addons directory defined in the local environment guide.

Do not edit Odoo Community or Enterprise source.

Do not modify the sibling `midvex_marketplace_foundry` repository; it is a reference only.

## Channel API docs rule

Before implementing a channel's payloads, the agent must verify the latest official API documentation.

Document the checked URL, date, and API version in the channel project folder (`API_RESEARCH.md`).

Do not rely only on memory, old snippets, third-party blog posts, or generated assumptions.

## Implementation order

1. Build `midvex_o_notification_foundry`.
2. Build Telegram MVP first.
3. Generalize the foundry after real Telegram integration needs are known.
4. Build Email.
5. Build Slack.
6. Build WhatsApp/SMS.
7. Add advanced features only after delivery queue, retry, and logs are stable.

## MVP scope

The MVP must support:

- channel/account configuration;
- channel registry;
- test connection;
- recipient linking (self-service, per user);
- message templates with variable rendering;
- notification rules (event → template → channel → audience);
- delivery queue with retry;
- structured delivery logs;
- basic dashboards;
- permission-controlled configuration and logs.

Delay:

- rich attachments/media;
- inbound conversational commands beyond `/link`;
- delivery analytics/reporting;
- per-user channel preference center beyond linking;
- SLA/escalation rules;
- bulk campaign sending.

## Security rules

- Do not commit bot tokens, webhook secrets, or API keys.
- Do not print credentials.
- Store credentials using Odoo configuration/security patterns.
- Mask secrets in logs.
- Use company-scoped credentials.
- Never use production channel credentials in test databases unless the user explicitly authorizes it.
- Avoid unrestricted sudo.
- Protect webhook endpoints; verify provider signatures/secret tokens.
- Redact recipient message-body content from default log verbosity where practical.
- Make all manual notification actions permission-controlled.

## Definition of done

A notification module is done only when:

- it installs cleanly;
- it upgrades cleanly;
- it has correct access rights;
- it supports multi-company;
- it does not duplicate queue/log/retry logic;
- it uses shared foundry queues and logs;
- it has tests;
- channel docs were verified;
- API research notes are updated;
- no secrets are exposed;
- README and changelog are updated.
