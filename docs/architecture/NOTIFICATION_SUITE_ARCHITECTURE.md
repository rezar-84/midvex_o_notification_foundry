# Notification Suite Architecture

## Goal

Build a reusable Odoo 19 multi-channel notification architecture.

The system should connect Odoo to:

- Telegram;
- Email;
- Slack;
- WhatsApp.

The architecture must minimize repeated code by centralizing common notification operations (queueing, retry, logging, permissions, recipient linking) in a foundry module.

## High-level architecture

```text
Odoo events (CRM, Sales, Inventory, ...)
        ↓
midvex_o_notification_foundry
        ↓
Channel adapters
        ↓
Telegram / Email / Slack / WhatsApp APIs
```

## Addon layout

```text
custom-addons/
├── midvex_o_notification_foundry/
├── midvex_o_notification_telegram/
├── midvex_o_notification_email/
├── midvex_o_notification_slack/
└── midvex_o_notification_whatsapp/
```

## Foundry responsibilities

The foundry owns notification channels, the channel adapter registry, credential abstraction, recipient linking (mapping `res.users`/`res.partner` to a channel identity), message templates and rendering, notification rules (event → template → channel → audience), the delivery queue, retries, rate-limit backoff, delivery logs, dashboards, and normalized payload contracts.

## Channel module responsibilities

Channel modules own authentication, endpoint URLs, request headers, payload transformation, response parsing, delivery-status mapping, channel error parsing, rate-limit interpretation, webhook/inbound-update parsing, and channel-specific linking behavior (e.g. Telegram's `/link` command).

## Key design principle

Channel modules return normalized data to the foundry. The foundry writes to Odoo (messages, logs, recipient state). Channel modules should not directly create or update foundry records outside the normalized DTOs the dispatcher passes them, unless a foundry extension explicitly delegates that behavior.

## Shared normalized flows

### Outbound delivery

```text
Business event (e.g. crm.lead created) → Notification rule match → Template render → Normalized Message DTO → Channel adapter payload → Telegram/Email/Slack/WhatsApp API
```

### Inbound events (webhooks)

```text
Channel webhook call → Channel adapter parser → Normalized Inbound Event DTO → Foundry inbound handler (e.g. recipient linking) → Odoo state update
```

### Recipient linking

```text
User requests link code → Foundry generates short-lived code → User sends code to channel (e.g. Telegram /link) → Channel adapter parses inbound → Foundry matches code → Recipient marked linked
```

## Extension strategy

Start with Telegram because it gives the first real implementation pressure (bot API, webhook, self-service linking). Avoid over-generalizing the foundry before one channel works.

After Telegram MVP:

- move reusable code from the Telegram module to the foundry;
- keep only Telegram-specific API code in the channel module;
- add Email, Slack, and WhatsApp using the same contract.

## Anti-patterns

Avoid one huge notification module, duplicated queue/retry/log logic per channel, plain-text credential/token logging, synchronous channel API calls inside the triggering transaction, hard-coded recipient/company/group IDs, unverified webhook payloads, and live API calls in automated tests.
