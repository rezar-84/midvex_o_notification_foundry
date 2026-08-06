# Project — Notification Foundry

## Module

```text
midvex_o_notification_foundry
```

## Purpose

Create the reusable engine for all multi-channel notifications.

This module provides shared Odoo-side infrastructure for notification channels, accounts, recipient linking, message templates, notification rules (event bindings), the delivery queue, retries, structured delivery logs, permissions, and dashboards.

## Channel modules

Channel modules depend on this foundry:

```text
midvex_o_notification_telegram
midvex_o_notification_email
midvex_o_notification_slack
midvex_o_notification_whatsapp
```

## MVP

The MVP supports one channel first — Telegram — then evolves into a stable shared engine as more channels are added.

## Non-goal

This module must not contain channel-specific API endpoint implementation.
