# Project — Telegram Notification Connector

## Module

```text
midvex_o_notification_telegram
```

## Depends on

```text
midvex_o_notification_foundry
```

## Purpose

Implement the Telegram channel adapter for the notification foundry: outbound message delivery, connection testing, and an inbound webhook for self-service recipient linking.

## Documentation verification

Verified against the official Telegram Bot API documentation at `https://core.telegram.org/bots/api` (Bot API 10.2, page dated 2026-07-14; checked 2026-08-01). See `API_RESEARCH.md`.

## MVP scope

- test connection (`getMe`);
- send a rendered message (`sendMessage`);
- register/inspect webhook (`setWebhook`, `getWebhookInfo`);
- verify inbound webhook calls via the secret-token header;
- parse `/link <code>` inbound commands for recipient linking;
- error parsing;
- delivery logs (via the foundry).
