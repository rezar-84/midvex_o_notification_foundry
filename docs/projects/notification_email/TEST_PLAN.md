# Test Plan — Email Connector

## Mock API tests (`addons/midvex_o_notification_email/tests/test_email_adapter.py`)

- test connection validates the configured outgoing server;
- send builds subject/body correctly and parses the result;
- error response parsing surfaces the provider's error shape.

All tests use inline fixture dicts and mocked transport — no live email sends.

## Foundry integration tests

Not duplicated per-channel. `midvex_o_notification_foundry/tests/test_notification_dispatch.py` already proves the generic rule/queue/registry pipeline against any registered adapter via an in-memory fake adapter.

## Not covered by automated tests (requires a real mail server)

- Real outgoing-server test connection.
- Live delivery of a rendered notification.

Status: **planned**, not yet implemented.
