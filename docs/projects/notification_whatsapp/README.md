# Project — WhatsApp Notification Connector

## Module

```text
midvex_o_notification_whatsapp
```

## Depends on

```text
midvex_o_notification_foundry
```

## Purpose

Implement the WhatsApp channel adapter for the notification foundry.

## Documentation verification

The agent must verify the latest official WhatsApp Business Platform (Cloud API) documentation (`https://developers.facebook.com/docs/whatsapp`) before implementation.

## MVP scope

- test connection;
- send a rendered template message (WhatsApp requires pre-approved message templates for business-initiated conversations);
- error parsing;
- sync logs.

Status: **planned**, not yet implemented. See `docs/roadmap/NOTIFICATION_ROADMAP.md` Phase 6.
