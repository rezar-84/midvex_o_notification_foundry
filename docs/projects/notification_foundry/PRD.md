# PRD — Notification Foundry

## Problem

Odoo needs to notify internal users across multiple channels when business events happen (starting with a CRM lead being created). If each channel integration is built independently, the project will duplicate account configuration, recipient management, templating, delivery queues, retries, logs, dashboards, and permission handling.

## Product goal

Build a reusable foundry module that centralizes common notification behavior and allows each channel module to stay thin.

## Users

- Odoo administrators
- sales/CRM team members (notification recipients)
- operations teams
- developers

## Business goals

- notify the right members immediately when a business event happens;
- manage multiple notification channels from one dashboard;
- reduce duplicate integration code per channel;
- keep channel-specific API logic isolated;
- make future channel integrations faster;
- give administrators visibility into delivery success/failure.

## Functional requirements

### FR-1 Notification channel model

The module must provide a shared channel catalog model (telegram, email, slack, ...).

### FR-2 Channel registry

The module must allow channel modules to register channel codes and adapters.

### FR-3 Notification account model

The module must provide a company-scoped account/credential model per channel.

### FR-4 Recipient linking

The module must link Odoo users to a channel identity (e.g. a Telegram chat id) through a self-service linking flow.

### FR-5 Message templates

The module must support reusable, model-bound message templates with variable rendering.

### FR-6 Notification rules

The module must bind a triggering event (model + operation) to a template, one or more channels, and an audience.

### FR-7 Delivery queue

The module must queue one message per (recipient × channel) and process it asynchronously.

### FR-8 Retry handling

Failed messages must be retryable with attempt counts and next-retry time, distinguishing retryable from non-retryable errors.

### FR-9 Structured logs

Every delivery attempt must produce an audit log entry.

### FR-10 Normalized DTOs

Channel adapters must communicate with the foundry using normalized data structures.

### FR-11 Multi-company support

All records must be company-aware.

### FR-12 Permissions

Only authorized users may configure channel accounts, rules, and view delivery logs; every user may manage their own recipient link.

### FR-13 Dashboard

The module must provide a single dashboard for accounts, rules, templates, the message queue, delivery logs, and recipients.

## Non-functional requirements

Odoo 19 compatible, no core modification, batch-safe, multi-company safe, testable without live channel APIs, rate-limit aware, secure credential handling, translatable UI, readable logs with PII-conscious redaction, channel-isolated failures.

## Non-goals for MVP

Rich attachments/media, delivery analytics/reporting, per-user channel preference beyond linking, SLA/escalation rules, bulk campaign sending, inbound conversational commands beyond `/link`.

## Acceptance criteria

- Foundry installs without any channel module.
- Foundry can register a test/dummy channel adapter.
- Foundry can create a notification rule and enqueue messages when its trigger fires.
- Foundry can process the queue through a fake adapter and record logs/state.
- Channel modules can reuse the same account, queue, log, and recipient models.
- No channel-specific endpoint is hard-coded in the foundry.
