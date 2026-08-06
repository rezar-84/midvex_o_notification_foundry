# PRD — Telegram Connector

## Goal

Connect Odoo to Telegram through the notification foundry so members can receive real-time notifications (starting with "CRM lead created") in Telegram.

## Functional requirements

- Configure a Telegram bot token per notification account.
- Test connection.
- Send a rendered message to a linked recipient's chat.
- Register a webhook for inbound updates.
- Verify inbound webhook calls using Telegram's secret-token header.
- Parse `/link <code>` commands from inbound messages to link a recipient's chat id.
- Handle rate limits and retryable errors.
- Log all API operations via the foundry.

## Provider-specific fields to verify

```text
bot_token, webhook secret_token, chat_id
```

Do not implement these blindly. Verify from the latest official docs.

## Non-goals for MVP

- rich media/attachments;
- inline keyboards/buttons;
- group chat notifications (individual user chats only);
- conversational commands beyond `/link`;
- message editing/deletion after send.
