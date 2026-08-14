# PRD — Conversation Foundry

## Provenance

The conversation slice of `varsco_omnichannel_messaging_project/02_PRD.md` and `03_REQUIREMENTS.md`. Full personas and journeys live in `../omnichannel_messaging/PRD.md`.

## Problem

The Notification Foundry can tell a customer something. It cannot hold a conversation with one. It has no thread, no session, no identity map, no assignment, no read state, and no concept of a message arriving that nobody asked for.

Today an inbound Telegram message that is not a slash command is stored as a `midvex.notification.inbound.event` row and then dropped. That is the whole of the platform's two-way capability.

## Goal

A provider-neutral conversation store and service API that any channel adapter can feed, and that CRM and Sales bridges can read, without either side knowing about the other's provider.

## In scope

- `midvex.conversation.thread` — the logical conversation, one per customer topic, spanning channels.
- `midvex.conversation.session` — one channel's leg of that thread.
- `midvex.conversation.message` — durable, immutable message records with delivery state.
- `midvex.conversation.identity` — the map from Odoo partners to channel identifiers.
- Assignment, with an audit trail.
- Status lifecycle: new → open → waiting_customer / waiting_agent → resolved → archived, with reopen.
- A service API the adapters and bridges call, so neither writes to the models directly.
- ACLs and record rules, extending the existing three-group ladder.

## Out of scope

- Provider payloads of any kind.
- CRM lead creation — `midvex_o_conversation_crm`.
- Quotation actions — `midvex_o_conversation_sale`.
- The agent inbox UI — phase 4.
- AI — phases 8–9, and per ADR-007 never a transport dependency.

## Requirements covered

FR-008 (inbox operations, model side), FR-011 (conversation events trigger notification rules), FR-012 (multi-company scoping), FR-014 (original language retained), FR-017 (audit).

## Acceptance

From `../omnichannel_messaging/ACCEPTANCE_CRITERIA.md`:

- one thread can contain multiple sessions;
- one session belongs to one company/account;
- inbound/outbound messages ordered consistently;
- resolve/reopen lifecycle works;
- assignment audited;
- cross-company access denied.

## Key design constraint

`thread.company_id == session.company_id == account.company_id` must hold on every outbound operation, enforced server-side, not by a view domain. See ADR-009 in `../omnichannel_messaging/` provenance and ADR-013 in `../notification_foundry/DECISIONS.md`.
