# Project — Conversation Foundry

## Module

```text
midvex_o_conversation_foundry
```

## Depends on

```text
midvex_o_notification_foundry
```

## Status

**Planned. Not started.** Roadmap phase 3.

## Purpose

Own persistent two-way customer communication: conversation threads, channel sessions, messages, external identities, assignment, status lifecycle, inbound event processing, and a provider-neutral conversation service API.

It is a **sibling** of the Notification Foundry, not a layer on top of it and not a replacement for it. See ADR-013.

```text
Business Event   -> Notification Foundry -> "send this notice"
Customer Message -> Conversation Foundry -> "maintain this dialogue"
```

## What it must not do

- become a second delivery queue — it reuses the foundry's;
- become a second adapter registry — it reuses `services/registry.py` (ADR-015);
- know anything about Meta or Telegram payload shapes;
- create CRM leads (that is `midvex_o_conversation_crm`);
- assign sales users from adapter code.

## Scope expansion note

The root `AGENTS.md` and both `notification_foundry/PRD.md` and `notification_telegram/PRD.md` list "inbound conversational commands beyond `/link`" as an explicit MVP non-goal. This project supersedes that non-goal. See ADR-018.

## Documents

| File | Source | Purpose |
|---|---|---|
| `PRD.md` | pack `02` (conversation slice) | What the foundry must do |
| `ARCHITECTURE.md` | pack `04` (conversation slice) | Where it sits and what it owns |
| `DATA_MODEL.md` | pack `05` | Seven models and their fields |
| `ADAPTER_CONTRACT.md` | pack `06` | Normalized DTOs and adapter interface |
| `TEST_PLAN.md` | pack `13` | Test layers and mandatory cases |
| `CHANGELOG.md` | — | Nothing yet |
