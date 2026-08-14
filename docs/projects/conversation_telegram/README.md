# Project — Telegram Conversation Connector

## Module

```text
midvex_o_conversation_telegram
```

## Depends on

```text
midvex_o_conversation_foundry
midvex_o_notification_telegram
```

## Status

**Planned. Not started.** Roadmap phase 10 (P2) — deliberately late.

## Purpose

Two-way Telegram customer conversation: inbound customer bot messages, identity linking, conversation creation, replies from the unified inbox, and status/error normalization.

## Why this is late in the roadmap and not early

Telegram is the channel with working transport code already, which makes it look like the cheap first win. It is not, for two reasons:

1. **Telegram is currently an internal staff channel, not a customer channel.** The bot's whole inbound vocabulary is `/link`, `/status`, `/mute`, `/unmute`, `/unlink`, `/help` — a self-service linking flow for employees. Customers do not message it. Building two-way conversation here delivers nothing to a customer until customers are pointed at it, which is a business decision, not a coding one.
2. **WhatsApp is where the customers are.** The roadmap's first milestone is a WhatsApp path end to end, precisely because that is where the unmet demand is.

So Telegram stays a notification channel through phases 1–9, and gains conversation only once the foundry it would plug into is proven.

## Do not regress what works

The existing `midvex_o_notification_telegram` adapter and webhook are in production use for lead alerts. This project must not:

- make the notification adapter inherit conversation models;
- change the `/notification/telegram/webhook/<account_id>` route's existing behavior;
- change the meaning of `midvex.notification.recipient` linking.

Share only transport and auth parsing helpers that are genuinely common. See the source pack's compatibility rule, carried into ADR-013.

## Account separation

The internal notification bot and a customer-facing bot may be the same provider, but they must be modelled as **separate accounts** when operationally necessary. Staff alerts and customer conversations arriving at one bot token is an operational trap: muting one mutes the other.

## Documents

| File | Source |
|---|---|
| `PRD.md` | pack `08` |
| `ARCHITECTURE.md` | pack `08` + `04` |
| `API_RESEARCH.md` | points at `../notification_telegram/API_RESEARCH.md` |
| `TEST_PLAN.md` | pack `13` |
