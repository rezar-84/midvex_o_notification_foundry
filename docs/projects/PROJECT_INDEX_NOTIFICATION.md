# Notification and Conversation Project Index

## Notification suite — event-driven outbound delivery

| Project | Module | Status | Docs |
|---|---|---:|---|
| Notification Foundry | `midvex_o_notification_foundry` | Implemented (MVP) | `notification_foundry/` |
| Telegram Connector | `midvex_o_notification_telegram` | Implemented (MVP) | `notification_telegram/` |
| WhatsApp Connector | `midvex_o_notification_whatsapp` | Implemented, never run live | `notification_whatsapp/` |
| Email Connector | `midvex_o_notification_email` | Planned | `notification_email/` |
| Slack Connector | `midvex_o_notification_slack` | Planned | `notification_slack/` |

## Conversation suite — persistent two-way customer communication

| Project | Module | Status | Docs |
|---|---|---:|---|
| Omnichannel Messaging | *(umbrella)* | Documented | `omnichannel_messaging/` |
| Conversation Foundry | `midvex_o_conversation_foundry` | Implemented (phase 3) | `conversation_foundry/` |
| WhatsApp Conversation | `midvex_o_conversation_whatsapp` | Implemented, never run live | `conversation_whatsapp/` |
| Website Live Chat | `midvex_o_conversation_webchat` | Documented, not started | `conversation_webchat/` |
| Telegram Conversation | `midvex_o_conversation_telegram` | Documented, not started | `conversation_telegram/` |
| Messaging API | `varsco_messaging_api` | Documented, not started | `messaging_api/` |

The two suites are siblings, not layers. See ADR-013 in `notification_foundry/DECISIONS.md`.

Start with `omnichannel_messaging/README.md` for the conversation half.
