# Project — Omnichannel Messaging

## Modules

```text
midvex_o_conversation_foundry     planned
midvex_o_conversation_whatsapp    planned
midvex_o_conversation_webchat     planned
midvex_o_conversation_telegram    planned
midvex_o_conversation_crm         planned
midvex_o_conversation_sale        planned
midvex_o_notification_whatsapp    in progress
varsco_messaging_api              planned
```

## Purpose

The umbrella project. It defines a reusable Odoo 19 omnichannel messaging layer for VARS and other companies, integrating WhatsApp, website live chat, and Telegram with CRM, Sales, Contacts, notification workflows, and optional AI assistance.

Notifications and conversations are deliberately separate concepts:

- **Notification Foundry** — event-driven one-way or transactional delivery. Already built.
- **Conversation Foundry** — persistent two-way customer communication. Not yet built.

They share channel/account abstractions and provider adapters where appropriate, but must not share business-state models blindly. See ADR-013.

## Provenance

This directory and its five sibling `conversation_*` / `messaging_api` directories were merged from the standalone documentation pack at `~/Projects/varsco_omnichannel_messaging_project/` (23 files, dropped 2026-08-14), per that pack's own `21_REPO_MERGE_MAP.md`. **The copy in this repository is canonical.** The originals are unversioned and should be treated as a historical drop.

Two corrections were applied during the merge rather than carried forward:

1. The pack describes the public website as Next.js. It is TanStack Start + Vite + React on Bun (`Websites/varsco_com`). See ADR-016.
2. The pack uses bare `conversation.*` Odoo model names. This repository's convention is a `midvex.` prefix. See ADR-014.

## Documents

| File | Source | Purpose |
|---|---|---|
| `PROJECT_BRIEF.md` | pack `01` | Business context, goals, boundaries |
| `PRD.md` | pack `02` | Personas, journeys, product principles |
| `REQUIREMENTS.md` | pack `03` | FR-001…020, NFR-001…010 |
| `ARCHITECTURE.md` | pack `04` | Module boundaries and pipelines |
| `SECURITY_MULTI_COMPANY.md` | pack `11` | Threat model, invariants, record rules |
| `AI_ASSISTANT_SPEC.md` | pack `12` | AI modes, guardrails, tool design |
| `ROADMAP.md` | pack `14` | Phases 0–12 |
| `ACCEPTANCE_CRITERIA.md` | pack `16` | Release gates and DoD |
| `RUNBOOK.md` | pack `18` | Operations and troubleshooting |

The pack's `05` (data model), `06` (adapter contract) and `13` (test plan) live in `../conversation_foundry/`. Its `07`, `08`, `09`/`10` live in the matching `conversation_*` and `messaging_api` directories. Its `17` (decisions) was folded into `../notification_foundry/DECISIONS.md` as ADR-013…018 rather than kept as a competing log.

## Initial milestone

A new customer sends a WhatsApp message to a company number and:

1. the webhook is validated;
2. the company is resolved;
3. the customer identity is matched or provisionally created;
4. a conversation is created;
5. an Odoo CRM lead is created when required;
6. the salesperson is notified;
7. the conversation appears in the Odoo inbox;
8. the salesperson replies from Odoo;
9. delivery/read states synchronize back to Odoo;
10. duplicate provider webhook retries do not duplicate messages or leads.

That milestone proves the reusable core. Do not start AI, media, advanced routing, or Telegram two-way work before this path is stable.

## Current status

Phases 0–2 are the active scope: the contract is frozen in this repository, and WhatsApp is being built as a real transport (outbound transactional, then verified idempotent inbound). Phases 3 onward — Conversation Foundry, CRM bridge, agent inbox, live chat, AI — are documented but not started.
