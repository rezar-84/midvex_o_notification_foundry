# Test Plan — Telegram Connector

## Mock API tests (`addons/midvex_o_notification_telegram/tests/test_telegram_adapter.py`)

- `test_connection` calls `getMe` and parses the bot `User` response;
- `send` builds `chat_id`/`text` correctly and parses a successful `Message` response into the Normalized Delivery Result DTO;
- `register_webhook` sends `url` and `secret_token` to `setWebhook`;
- error response parsing surfaces Telegram's `{ok, error_code, description}` shape, marking HTTP 429 (with `parameters.retry_after`) as retryable and 4xx auth errors as non-retryable;
- `parse_inbound` extracts `chat.id`, `from.username`, and a `/link <code>` command from a sample `Update` JSON body;
- webhook controller rejects a request whose `X-Telegram-Bot-Api-Secret-Token` header does not match the account's stored secret.

All tests use inline fixture dicts and a monkeypatched `urlopen` on the adapter's module — no live API calls, no real bot token.

## Foundry integration tests

Not duplicated per-channel. `midvex_o_notification_foundry/tests/test_notification_dispatch.py` already proves the generic rule/queue/registry pipeline (rule match, template render, message enqueue, fake-adapter send, log/state assertions, idempotency) against any registered adapter via an in-memory fake adapter. Telegram's adapter unit tests plus that shared suite are the coverage for this module.

## Not covered by automated tests (requires a real bot token and public URL)

- Real Telegram credential test connection (`getMe`).
- Live `setWebhook` registration against a publicly reachable HTTPS URL.
- An end-to-end `/link` flow with a real Telegram account.
- Live delivery of a "CRM lead created" notification.
