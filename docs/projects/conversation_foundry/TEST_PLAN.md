# Test Plan — Conversation Foundry and Omnichannel Messaging

## Provenance

Merged from `varsco_omnichannel_messaging_project/13_TEST_PLAN.md`. Covers the whole omnichannel effort, not only the conversation foundry.

## Test philosophy

Use TDD for domain services and adapter normalization.

No automated test may depend on a live Meta or Telegram API.

Use captured/synthetic fixtures with secrets removed.

This matches the existing suite: `test_telegram_adapter.py` monkeypatches `urlopen`, and `test_notification_dispatch.py` / `test_rate_limits.py` use hand-written fake adapters (`MockAdapter`, `ThrottledAdapter`). Follow that pattern rather than adding a mocking library.

## Test layers

### Unit tests
- phone normalization;
- identity matching;
- company invariant;
- conversation state transitions;
- adapter payload conversion;
- status mapping;
- retry classification;
- AI mode rules.

### Odoo transaction tests
- model constraints;
- record rules;
- lead creation;
- assignment;
- notification event emission;
- template selection;
- access rights;
- cross-company denial.

### HTTP/controller tests
- webhook verification;
- invalid signature;
- valid inbound;
- duplicate inbound;
- public chat session auth;
- agent API auth;
- rate-limit hooks.

### Integration tests with mocked provider
- outbound accepted;
- provider 4xx;
- provider 5xx;
- timeout;
- rate limit;
- delivery webhook;
- read webhook;
- unknown event.

### End-to-end staging
Use test credentials/number only:
- customer sends WhatsApp;
- Odoo receives;
- lead/thread created;
- Telegram internal alert;
- Odoo reply;
- customer receives;
- status update returns.

## Mandatory WhatsApp cases

- unknown phone;
- known partner;
- multiple possible partner matches;
- E.164 variations;
- destination company resolution;
- wrong-company account send blocked;
- duplicated webhook;
- out-of-order delivery statuses;
- invalid token;
- expired/revoked token;
- provider outage;
- policy/template rejection;
- resolved conversation receives new message;
- unsupported media event.

## Live chat cases

- create session;
- expired token;
- guessed ID;
- spam rate limit;
- customer reload/reconnect;
- multiple browser tabs;
- agent response;
- offline state;
- handoff to WhatsApp.

## Security tests

- ACL matrix;
- record rules;
- company crossover;
- forged webhook;
- replay;
- oversized payload;
- HTML/script content;
- secret redaction.

## Regression

Existing Telegram notification tests must remain green. The suite stood at **120 tests, 0 failed, 0 errors** on merged `main` as of 2026-08-10; that number is the floor, not a target.

## Performance

Measure:
- webhook acknowledgement time;
- queued inbound processing latency;
- conversation list query time;
- message history pagination;
- realtime fanout behavior.

## Test data

Provide factories for:
- companies;
- accounts;
- partners;
- leads;
- identities;
- conversations;
- sessions;
- inbound envelopes;
- messages.

`addons/midvex_o_notification_foundry/tests/common.py` already provides `ensure_channel`. Extend that file rather than starting a parallel helpers module.

## Release gate

No production deployment unless:
- unit/integration suite passes;
- upgrade test passes;
- multi-company tests pass;
- no live secret in repository;
- staging E2E succeeds.

## Two traps this suite has already fallen into

Both cost a session to diagnose and are easy to repeat:

- **Adapter objects are not rolled back between tests.** The registry holds one instance per `channel_code` for the process lifetime, so a class-level `send_calls` list accumulates across test methods. Reset it in `setUp` or your call-count assertions silently inherit the previous test's sends.
- **Running a cron in `odoo-bin shell` commits.** `_cron_process_time_based_actions` calls `ir.cron._commit_progress()` mid-run, so a probe that prints "rolled back" can still leave a posted invoice and a queued message behind. Probe on a scratch database, never on one people open.
