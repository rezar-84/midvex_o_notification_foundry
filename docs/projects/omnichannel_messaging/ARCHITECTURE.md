# Architecture — Omnichannel Messaging

## Provenance

Merged from `varsco_omnichannel_messaging_project/04_ARCHITECTURE.md`. Module names below use this repository's `midvex.`-prefixed conventions (ADR-014).

## Context

The platform already has an Odoo Notification Foundry for event-driven delivery. Two-way chat adds conversation lifecycle, inbound identity, assignment, and CRM context.

The architecture therefore introduces a sibling Conversation Foundry. See ADR-013.

## Target architecture

```text
Customers
   |
   +-------------------+--------------------+
   |                   |                    |
WhatsApp            Telegram             Website
   |                   |                 Live Chat
Meta Cloud         Bot API                  |
   +-------------------+--------------------+
                       |
                Channel Adapters
                       |
               Conversation Foundry
                       |
      +----------------+------------------+
      |                |                  |
   Contacts           CRM                Sales
      |                |                  |
      +----------------+------------------+
                       |
                     Odoo
                       |
             Notification Foundry
                       |
            internal/customer alerts
```

## Module boundaries

### `midvex_o_notification_foundry` — built
Owns:
- outbound notification event/rule/template behavior;
- delivery queue;
- retry;
- delivery logs;
- shared channel/account registry;
- credentials abstraction;
- notification recipient linking.

Must not become the canonical conversation store.

### `midvex_o_conversation_foundry` — planned
Owns:
- conversation thread;
- channel session;
- message;
- external identity;
- assignment;
- status lifecycle;
- inbound event processing;
- generic conversation service API;
- channel-neutral audit metadata.

### `midvex_o_conversation_whatsapp` — planned
Owns:
- WhatsApp inbound parser;
- webhook verification;
- outbound conversation payloads;
- provider error/status mapping;
- WhatsApp policy/window capabilities;
- provider message IDs;
- WhatsApp identity normalization.

### `midvex_o_notification_whatsapp` — in progress
Owns:
- event-driven transactional WhatsApp sending through Notification Foundry;
- provider template mapping;
- delivery results.

Provider transport helpers are shared with the conversation module through a single client, not duplicated. See ADR-017.

### `midvex_o_conversation_webchat` — planned
Owns:
- web chat session behavior;
- visitor/session tokens;
- online presence;
- typing/read-state semantics if supported;
- conversion to persistent contact/lead identity.

### `midvex_o_conversation_telegram` — planned, phase 10
- two-way Telegram customer conversation;
- normalized inbound/outbound messages.

### `midvex_o_conversation_crm` — planned
Owns:
- linking threads to `crm.lead`;
- lead creation policies;
- lead summary/activity events;
- classification field mapping.

### `midvex_o_conversation_sale` — planned
Owns:
- linking thread to quotation/order;
- actions to create/open quotation;
- sales-originated conversation events.

### `varsco_messaging_api` — planned
Headless API for the frontend:
- customer web chat;
- authenticated agent inbox if implemented outside Odoo;
- no provider credentials;
- company-aware authorization.

## Core separation

```text
Business Event
  -> Notification Foundry
  -> "send this notice"

Customer Message
  -> Conversation Foundry
  -> "maintain this dialogue"
```

Conversation events may emit Notification Foundry events such as:
- `conversation.created`
- `conversation.unassigned`
- `conversation.customer_replied`
- `conversation.sla_warning`

## Webhook pipeline

```text
Provider
 -> HTTPS endpoint
 -> signature/verification
 -> store immutable inbound envelope
 -> dedupe
 -> fast acknowledgement
 -> queued processing
 -> adapter normalize()
 -> conversation service
 -> CRM matching
 -> Notification Foundry event
```

Heavy AI/CRM work must not block provider webhook acknowledgement.

In the current phase the pipeline is implemented only as far as *dedupe → fast acknowledgement*. The queued-processing tail requires Conversation Foundry.

## Outbound pipeline

```text
Agent UI / business rule
 -> validate company/account/permissions
 -> create message in queued state
 -> queue job
 -> adapter send()
 -> normalized provider result
 -> update message
 -> delivery webhook updates final state
```

This is the existing foundry's pipeline. WhatsApp plugs into it as another adapter; it does not get its own.

## Realtime strategy

Preferred abstraction:
- Odoo bus where practical;
- SSE/WebSocket gateway for headless chat;
- avoid uncontrolled polling.

The exact transport may be chosen after compatibility testing with the current Odoo deployment and reverse proxy.

## Provider transport reuse

Where notification WhatsApp and conversation WhatsApp share:
- auth;
- API client;
- error parsing;
- status mapping;

they use one small provider client rather than duplicating code.

Do not couple Conversation Foundry directly to WhatsApp classes.

## Relationship to the existing suite architecture

`docs/architecture/NOTIFICATION_SUITE_ARCHITECTURE.md` remains authoritative for the notification half. This document extends it; it does not replace it. Where they disagree about the foundry's responsibilities, the suite architecture wins.
