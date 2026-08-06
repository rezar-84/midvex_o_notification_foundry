# Test Plan — Slack Connector

## Mock API tests (`addons/midvex_o_notification_slack/tests/test_slack_adapter.py`)

- test connection parses the auth-check response;
- send builds the message payload correctly and parses the result;
- error response parsing surfaces Slack's error shape.

All tests use inline fixture dicts and mocked transport — no live API calls.

## Foundry integration tests

Not duplicated per-channel. `midvex_o_notification_foundry/tests/test_notification_dispatch.py` already proves the generic rule/queue/registry pipeline against any registered adapter via an in-memory fake adapter.

## Not covered by automated tests (requires a real workspace/bot token)

- Real Slack credential test connection.
- Live delivery of a rendered notification.

Status: **planned**, not yet implemented.
