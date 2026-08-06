# Test Plan — WhatsApp Connector

## Mock API tests (`addons/midvex_o_notification_whatsapp/tests/test_whatsapp_adapter.py`)

- test connection parses the phone-number status response;
- send builds the template message payload correctly and parses the result;
- error response parsing surfaces the provider's error shape.

All tests use inline fixture dicts and mocked transport — no live API calls.

## Foundry integration tests

Not duplicated per-channel. `midvex_o_notification_foundry/tests/test_notification_dispatch.py` already proves the generic rule/queue/registry pipeline against any registered adapter via an in-memory fake adapter.

## Not covered by automated tests (requires a real WhatsApp Business account)

- Real credential test connection.
- Live delivery of an approved template message.

Status: **planned**, not yet implemented.
