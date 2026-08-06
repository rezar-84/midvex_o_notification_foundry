# Test Plan — Notification Foundry

## Unit tests

- adapter registry resolves channel;
- retry policy;
- DTO validation;
- idempotency key generation;
- link-code generation and expiry.

## ORM tests

- create notification channel;
- create notification account;
- create recipient;
- create template;
- create rule;
- create message;
- create log.

## Security tests

- notification manager can view accounts;
- unauthorized user cannot edit credentials;
- any user can manage their own recipient link, not another user's;
- delivery logs are protected from non-members.

## Multi-company tests

- account per company;
- rules isolated by company;
- messages isolated by company.

## Rendering tests

- template renders variables from the triggering record;
- missing variable falls back gracefully;
- template body cannot execute arbitrary code.

## Queue tests

- pending message is processed;
- failed message records error;
- retryable error schedules next retry;
- non-retryable error stops retrying;
- duplicate trigger for the same event does not create a duplicate message.

## Automation-wiring tests

- creating a `crm.lead` matching an active rule enqueues one message per (recipient × channel);
- an inactive rule does not enqueue;
- a recipient in `pending` (unlinked) state is skipped, not errored.

## Channel adapter stub tests

Create a dummy channel adapter and verify the foundry can call test connection, send, and process a delivery result through it, without any network access.
