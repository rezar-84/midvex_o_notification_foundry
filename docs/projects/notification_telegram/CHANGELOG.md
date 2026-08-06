# Changelog — Telegram Connector

## Unreleased

- Initial documentation.
- Verified the official Telegram Bot API (`core.telegram.org/bots/api`, Bot API 10.2) — see `API_RESEARCH.md`.
- Implemented `midvex_o_notification_telegram` adapter: `test_connection`, `send`, `register_webhook`, `parse_inbound`, `parse_error`.
- Implemented the inbound webhook controller with secret-token verification and `/link <code>` recipient-linking support.
- Wired the first foundry notification rule: "CRM lead created" → Telegram, for the demo/starter audience.
