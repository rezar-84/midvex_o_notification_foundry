# API Research — Telegram

## Verification

- **Checked:** 2026-08-01
- **API:** Telegram Bot API (`api.telegram.org`)
- **Source:** `https://core.telegram.org/bots/api` — official documentation, fetched directly (no 403/WAF block, unlike N11's support pages). Page shows **Bot API version 10.2**, dated 2026-07-14.
- **Scope:** authentication, `getMe`, `sendMessage`, `setWebhook`/`deleteWebhook`/`getWebhookInfo`, the `Update`/`Message` object shape, webhook secret-token verification, and the error response shape.

## Confirmed

- **Base URL:** `https://api.telegram.org/bot<token>/<METHOD_NAME>` — the bot token is embedded directly in the URL path, not sent as a header. Token format: `123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11`.
- **`getMe`** — no parameters; returns a `User` object (`id`, `is_bot`, `first_name`, `username`, ...). Used as `test_connection`.
- **`sendMessage`** — required: `chat_id`, `text` (1–4096 chars). Relevant optional: `parse_mode` (HTML/Markdown/MarkdownV2). Returns a `Message` object on success.
- **`setWebhook`** — required: `url` (HTTPS; empty string removes the webhook). Optional: `secret_token` (1–256 chars, `A-Z a-z 0-9 _ -` only), `max_connections` (1–100, default 40), `allowed_updates`, `drop_pending_updates`. Returns `true` on success.
- **`deleteWebhook`** — optional `drop_pending_updates`. Returns `true`.
- **`getWebhookInfo`** — no parameters; returns `WebhookInfo` (`url`, `has_custom_certificate`, `pending_update_count`, `last_error_date`, `last_error_message`, `max_connections`, `allowed_updates`). Used for the account's connection/webhook status display.
- **Inbound webhook body** — Telegram POSTs an `Update` object as JSON: `{"update_id": ..., "message": {"message_id": ..., "date": ..., "chat": {"id": ...}, "from": {...}, "text": "..."}}`. `message.chat.id` is the value stored as `midvex.notification.recipient.external_id`.
- **Secret-token verification** — when `secret_token` was set via `setWebhook`, every webhook POST carries header `X-Telegram-Bot-Api-Secret-Token` with that exact value. The controller must reject any request where this header does not match the account's stored `webhook_secret`.
- **Error shape:** `{"ok": false, "error_code": <int>, "description": "<string>", "parameters": {...}}` — `parameters.retry_after` is present on HTTP 429 responses.

## Open gaps — unconfirmed by the official page, handled defensively

1. **Rate limits — confirmed 2026-08-10** at `https://core.telegram.org/bots/faq` (the Bot API reference page still states none; the FAQ does). Quoted:

   - *"In a single chat, avoid sending more than one message per second."*
   - *"For bulk notifications, bots are not able to broadcast more than about 30 messages per second, unless they enable paid broadcasts to increase the limit."*
   - *"In a group, bots are not be able to send more than 20 messages per minute."* — **the group limit is the one a notification rule breaches first**, and it was not recorded here before.
   - *"We may allow short bursts that go over this limit, but eventually you'll begin receiving 429 errors."*

   So these are sustained rates to stay under, not hard walls. They are declared on `TelegramAdapter` as `rate_limit_chat_seconds`, `rate_limit_group_per_minute` and `rate_limit_global_per_second`; the foundry reads them off the adapter and defers messages that would breach them. A 429 is retryable and honours `retry_after` from the Error contract rather than any hard-coded delay.
2. **`max_connections` tuning** — left at Telegram's default (40) for MVP; not exposed as a configurable field yet.
3. **Certificate handling for self-signed certs** (`certificate` parameter on `setWebhook`) — out of scope; the MVP assumes a webhook URL with a valid, publicly-trusted TLS certificate (e.g. via a reverse proxy/tunnel), not a self-signed cert uploaded to Telegram.

## Implementation note

`allowed_updates` is not restricted in the MVP `register_webhook` call — the adapter accepts the default update set, since only `message` updates are parsed by `parse_inbound` in this pass; unrecognized update types are stored in `midvex.notification.inbound.event` but not acted on.

Automated tests use inline fixture dicts and a monkeypatched `urlopen`, not live API calls, per this project's development standards.
