# Architecture — Telegram Connector

## Module structure

```text
midvex_o_notification_telegram/
├── __init__.py
├── __manifest__.py
├── services/
│   ├── __init__.py
│   └── telegram_adapter.py
├── controllers/
│   ├── __init__.py
│   └── telegram_webhook.py
├── data/
│   └── telegram_channel.xml
└── tests/
    ├── __init__.py
    └── test_telegram_adapter.py
```

This mirrors the marketplace suite's proven single-file adapter shape (`midvex_l10n_tr_marketplace_trendyol`/`_n11`): one adapter file, no `models/`, `views/`, or `security/` of its own — it reuses the foundry's `group_notification_*` groups and record models as-is. The only addition versus the marketplace adapters is a `controllers/` package, because Telegram is the first channel that receives inbound webhook calls (the marketplace adapters are outbound-only).

## Foundry integration

The Telegram adapter implements the notification foundry's adapter contract — `test_connection(account)`, `send(account, message_dto)`, `register_webhook(account, webhook_url, secret_token)`, `parse_inbound(raw_payload)`, `parse_error(response_or_exception)` — and is registered via `@register_adapter` from `midvex_o_notification_foundry.services.registry`. It does not create or touch foundry records directly beyond what the webhook controller does through the foundry's own recipient-linking method.

## Adapter responsibilities (`services/telegram_adapter.py`)

- Bot-token URL construction (`https://api.telegram.org/bot<token>/<method>`).
- Request/response handling via `urllib.request` (stdlib only, matching the marketplace suite's minimal-footprint convention), with Telegram's `{ok, error_code, description}` error shape parsed into actionable `UserError` messages.
- `test_connection` → `getMe`.
- `send` → `sendMessage` with `chat_id` (the recipient's linked `external_id`) and rendered `text`.
- `register_webhook` → `setWebhook` with `url` and `secret_token`.
- `parse_inbound` → normalizes a Telegram `Update` JSON body into the foundry's Normalized Inbound Event DTO, extracting a `/link <code>` command if present.

## Webhook controller (`controllers/telegram_webhook.py`)

- Route: `POST /notification/telegram/webhook/<int:account_id>`, `auth='public'`, `csrf=False` (Telegram calls this endpoint directly, unauthenticated by Odoo session).
- Verifies the `X-Telegram-Bot-Api-Secret-Token` header against the account's stored `webhook_secret` before doing anything else; rejects with 403 on mismatch.
- Creates a `midvex.notification.inbound.event` record (raw payload, admin-only) for audit.
- If the parsed update contains a `/link <code>` command, calls `env['midvex.notification.recipient'].sudo().process_link_code(code, chat_id, username)` — a generic foundry method, keeping Telegram-specific parsing in the adapter/controller and generic state changes in the foundry.

## Deferred (not in this pass)

- Rich message formatting (`parse_mode`, inline keyboards).
- Any inbound command other than `/link`.
- Group/channel chat targets — only individual user chats are supported in the MVP.
