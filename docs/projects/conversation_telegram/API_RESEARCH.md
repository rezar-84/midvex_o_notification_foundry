# API Research — Telegram Conversation Connector

The Telegram Bot API research is maintained in one place:

**→ `../notification_telegram/API_RESEARCH.md`**

Verified against `https://core.telegram.org/bots/api` (Bot API 10.2, page dated 2026-07-14; checked 2026-08-01) for the notification connector.

## To verify before this project starts

The existing research covers `getMe`, `sendMessage`, `setWebhook`, `getWebhookInfo` and the secret-token header — everything the notification adapter needs. Two-way conversation needs more, and the API will have moved on by then:

- inbound `update_id` semantics and the exact dedupe guarantee Telegram offers on retries;
- `message` vs `edited_message` vs `channel_post` handling;
- reply threading (`reply_to_message`) and whether it maps usefully onto `reply_to_external_id`;
- read receipts — whether the Bot API exposes any, or whether `supports_read_receipts` is simply false for this channel;
- typing indicators (`sendChatAction`) and whether they are worth wiring;
- media download flow for inbound attachments (phase 11).

Re-check the version and date at that time. Do not assume the notes above are still current when this phase begins.
