# PRD — Telegram Conversation Connector

## Provenance

Merged from `varsco_omnichannel_messaging_project/08_TELEGRAM_SPEC.md`.

## Current state

Telegram already functions as an internal notification channel through Notification Foundry.

This behavior must remain stable.

Today, an inbound Telegram message that is not a slash command is written to `midvex.notification.inbound.event` with `event_type = 'message'` and then dropped. The parser extracts the text; the controller only branches on `command`. Free-text inbound is a stored-and-ignored dead end — by design, not by oversight.

## Phase 1

No mandatory customer-chat changes.

Continue using Telegram for:
- new lead notifications;
- failed messaging alerts;
- high-priority conversation alerts;
- optional supervisor escalation.

## Phase 2 (roadmap phase 10)

Add `midvex_o_conversation_telegram`.

Features:
- inbound customer bot messages;
- identity linking;
- conversation creation;
- replies from unified inbox;
- status/error normalization;
- optional `/start` or linking workflow.

## Separation

Internal notification Telegram account and customer-facing Telegram bot may be the same provider but must be modeled as separate accounts/purposes when operationally necessary.

## Security

- validate Telegram webhook secret/token mechanisms supported by current API;
- never expose bot token to browser;
- dedupe updates using provider update IDs;
- company-scope account configuration.

The existing webhook already verifies `X-Telegram-Bot-Api-Secret-Token`. Note its current fail-open behavior when no secret is configured on the account — acceptable for a staff linking bot, and something to revisit before the same endpoint carries customer conversations.

## Compatibility

Do not force the existing notification adapter to inherit conversation models.
Share only transport/auth parsing helpers that are truly common.

## What Telegram gives that WhatsApp does not

Worth remembering when this phase arrives: no 24-hour messaging window, no template pre-approval, no per-recipient 6-second throttle. A Telegram conversation can be replied to freely at any time. That makes it the better channel for long-running B2B threads — and the reason not to treat WhatsApp's constraints as universal when designing the conversation foundry's send path.
