# Project — Email Notification Connector

## Module

```text
midvex_o_notification_email
```

## Depends on

```text
midvex_o_notification_foundry
```

## Purpose

Implement the Email channel adapter for the notification foundry.

## Documentation verification

The agent must verify Odoo's own `mail.mail`/`ir.mail_server` capabilities (and, if a transactional email provider is chosen instead, that provider's official API docs) before implementation.

## MVP scope

- test connection (outgoing mail server check);
- send a rendered message;
- error parsing;
- sync logs.

Status: **planned**, not yet implemented. See `docs/roadmap/NOTIFICATION_ROADMAP.md` Phase 4.
