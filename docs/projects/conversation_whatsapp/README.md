# Project — WhatsApp Conversation Connector

## Module

```text
midvex_o_conversation_whatsapp
```

## Depends on

```text
midvex_o_conversation_foundry
midvex_o_notification_whatsapp
```

## Status

**Planned. Not started.** Requires the Conversation Foundry (phase 3).

## Purpose

Two-way WhatsApp customer conversation: inbound message parsing into conversation threads, outbound conversation payloads, provider error and status mapping, the customer-service messaging window and template policy, and WhatsApp identity normalization.

## Relationship to `midvex_o_notification_whatsapp`

Two modules, one provider, one transport client. See ADR-017.

| | `notification_whatsapp` | `conversation_whatsapp` |
|---|---|---|
| Trigger | An Odoo business event | A customer message |
| Direction | Outbound only | Two-way |
| State | A delivery queue row | A durable thread |
| Owns | Template mapping, delivery results | Threading, window policy, identity |
| Shares | `services/whatsapp_client.py` — auth, base URL, error parsing, status mapping | same |

The webhook endpoint is shared too. One provider callback URL per account serves both: statuses feed the notification queue, customer messages feed the conversation foundry. Registering two endpoints for one phone number would mean Meta delivering each event to only one of them.

## Provider

Official Meta WhatsApp Cloud API, direct, no BSP. See ADR-003 in the source pack, carried into `../notification_foundry/DECISIONS.md`. Full verified API details are in `API_RESEARCH.md`.

## Documents

| File | Source |
|---|---|
| `PRD.md` | pack `07` |
| `ARCHITECTURE.md` | pack `07` + `04` |
| `API_RESEARCH.md` | shared with `../notification_whatsapp/API_RESEARCH.md` |
| `TEST_PLAN.md` | pack `13`, WhatsApp cases |
