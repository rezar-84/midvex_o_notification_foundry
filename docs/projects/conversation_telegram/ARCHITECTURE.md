# Architecture — Telegram Conversation Connector

## Provenance

The Telegram slice of `varsco_omnichannel_messaging_project/04_ARCHITECTURE.md` and `08_TELEGRAM_SPEC.md`.

## Owns

- two-way Telegram customer conversation;
- normalized inbound/outbound messages for the conversation foundry;
- Telegram identity linking to `midvex.conversation.identity`.

## Does not own

- the transport — `services/telegram_adapter.py` in `midvex_o_notification_telegram` already implements `test_connection`, `send`, `register_webhook`, `parse_inbound`, `parse_error` and the rate-limit attributes. Import it; do not fork it.
- staff recipient linking (`/link` and friends) — that stays where it is.
- threading, assignment, state — the conversation foundry.

## The webhook fork

One bot token means one webhook URL. If a customer-facing bot is a separate account, it gets its own `account_id` and the existing route already distinguishes them. If it is the *same* bot, the controller must fork on who is talking:

```text
POST /notification/telegram/webhook/<account_id>
        |
   verify X-Telegram-Bot-Api-Secret-Token
        |
   store midvex.notification.inbound.event
        |
   +----------------+------------------+
   |                                   |
 command (/link, /status, ...)    free text
   |                                   |
 existing staff linking flow      conversation foundry
 — unchanged                      — new
```

The existing branch must keep behaving exactly as it does. The new branch is the one that was previously a no-op.

Preferring a separate account for customers avoids this fork entirely, and avoids the operational trap of staff alerts and customer messages sharing a mute switch. Decide it with an ADR when the phase starts.

## Identity

Telegram identifies a person by a numeric chat ID, optionally a username. The chat ID is stable and is the matching key; the username is mutable and is display only. Never match on username.

Note the difference from WhatsApp: there is no phone number, so a Telegram identity cannot be merged with a WhatsApp identity by normalization alone. Linking the two to one partner is an explicit act — a customer volunteering it, or an agent confirming it — not an inference.

## Rate limits

Already encoded on the existing adapter as class attributes: 1 second per chat, 20 per minute per group, 30 per second globally. The foundry throttles per message, not per batch, and defers rather than sleeping. Conversation replies go through the same path and inherit this for free — which is the point of not forking the adapter.

## Fail-open verification

`secret_token_is_valid` returns `True` when the account has no `webhook_secret` configured. For a staff linking bot that is a reasonable convenience. For an endpoint carrying customer conversations it is an unauthenticated write path, and it should be tightened to fail closed before this module ships.
