# Test Plan — Telegram Conversation Connector

## Provenance

`varsco_omnichannel_messaging_project/13_TEST_PLAN.md`, Telegram slice. General layers are in `../conversation_foundry/TEST_PLAN.md`.

## The regression that matters most

`addons/midvex_o_notification_telegram/tests/test_telegram_adapter.py` (8 classes) and the foundry's dispatch tests must stay green, unchanged, throughout. This project touches a webhook that is in production use for lead alerts. Any change to `/link`, `/status`, `/mute`, `/unmute`, `/unlink` or `/help` behavior is a defect, not a refactor.

## New cases

| Case | Layer | Asserts |
|---|---|---|
| Free-text inbound creates a conversation | controller | previously a no-op; now threads |
| Command inbound still runs the staff flow | controller | fork is correct, existing branch untouched |
| Duplicate `update_id` creates one record | controller | dedupe on the provider update identifier |
| Missing secret token rejected | controller | fail **closed** once customers are on this endpoint |
| Identity matches on chat ID, not username | unit | username is mutable and display-only |
| Username change does not create a second identity | unit | |
| Reply from the inbox reaches `send()` | transaction | reuses the existing adapter, no fork |
| Per-chat throttle applies to conversation replies | integration | inherited from the existing rate-limit attributes |
| Customer account and staff account are isolated | transaction | muting one does not mute the other |

## Fixture rule

Captured Telegram updates only, with chat IDs, usernames, names and message bodies replaced. No live Bot API call in any test, and no real bot token in any fixture — the repo's secret scan must pass over all of them.

## Adapter instance leakage

The registry holds one adapter instance per `channel_code` for the process lifetime, so any call-recording attribute on it accumulates across test methods. Reset in `setUp`. The existing suite already hit this; do not rediscover it.
