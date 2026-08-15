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

**Implemented (phase 3).** Version `19.0.1.0.0`, 69 tests.

A provider-neutral conversation can be created, threaded, assigned, replied to,
resolved and reopened. No channel is wired to it yet — that is
`midvex_o_conversation_whatsapp`, and it is the next step.

## Purpose

Own persistent two-way customer communication: conversation threads, channel
sessions, messages, external identities, assignment, status lifecycle, inbound
event processing, and a provider-neutral conversation service API.

It is a **sibling** of the Notification Foundry, not a layer on top of it and
not a replacement for it. See ADR-013.

```text
Business Event   -> Notification Foundry -> "send this notice"
Customer Message -> Conversation Foundry -> "maintain this dialogue"
```

## The service API is the entry point

Adapters and bridges call `services/conversation.py`; they do not `create()` on
the models. That seam is what keeps the company invariant, the state machine and
the audit trail enforceable in one place rather than re-implemented slightly
differently by each channel.

```python
from odoo.addons.midvex_o_conversation_foundry.services import conversation

identity = conversation.ensure_identity(env, company, 'whatsapp', '+905111111111')
thread   = conversation.ensure_thread(env, company, identity)
session  = conversation.open_session(env, thread, account, '+905111111111')

conversation.record_inbound(env, session, normalized_inbound_dto)
conversation.queue_outbound(env, session, 'Yes, we ship weekly.')
conversation.apply_status(env, account, 'wamid.X', 'read')
```

## What it does not do

- Know what WhatsApp is. It is tested against an in-memory fake channel, which
  is the point: proving it against WhatsApp would prove the WhatsApp module.
- Run a second delivery queue. Replies raise a job in the notification
  foundry's one queue and inherit its retry, throttling and delivery logging.
  See ADR-020.
- Create CRM leads or open quotations — `midvex_o_conversation_crm` and
  `_sale`, phase 4.
- Anything AI. Phase 8, and per ADR-007 never a transport dependency.

## Scope expansion note

The root `AGENTS.md` and two PRDs listed "inbound conversational commands beyond
`/link`" as an explicit MVP non-goal. This project supersedes that for customer
conversations; it still holds for the notification modules. See ADR-018.

## Documents

| File | Purpose |
|---|---|
| `PRD.md` | What the foundry must do |
| `ARCHITECTURE.md` | Where it sits and what it owns |
| `DATA_MODEL.md` | The models and their fields |
| `ADAPTER_CONTRACT.md` | Normalized DTOs, reconciled onto the existing registry |
| `TEST_PLAN.md` | Test layers and mandatory cases |
| `CHANGELOG.md` | What shipped |
