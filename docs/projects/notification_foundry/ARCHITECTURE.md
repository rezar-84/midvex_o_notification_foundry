# Architecture — Notification Foundry

## Dependencies

```python
"depends": [
    "base",
    "mail",
]
```

`mail` is required for `mail.thread`/`mail.activity.mixin` chatter on account/rule records and for reusing `mail.render.mixin` to render templates. Review exact dependencies before implementation (e.g. `crm` is only needed by the demo notification rule data, not by the foundry's Python code, so it is not a hard dependency).

## Proposed module structure

```text
midvex_o_notification_foundry/
├── __init__.py
├── __manifest__.py
├── models/
│   └── notification.py
├── services/
│   ├── registry.py
│   └── dispatcher.py
├── security/
│   ├── notification_security.xml
│   └── ir.model.access.csv
├── views/
│   ├── notification_views.xml
│   └── notification_menus.xml
├── data/
│   └── notification_cron.xml
└── tests/
    ├── common.py
    ├── test_notification_foundry.py
    └── test_notification_dispatch.py
```

## Menus

```text
Notifications
├── Message Queue
├── Delivery Logs
├── Recipients
├── Configuration
│   ├── Accounts
│   ├── Rules
│   └── Templates
```

## Service ownership

- `services/registry.py` resolves a channel code to a channel adapter instance.
- `services/dispatcher.py::enqueue_event` matches active rules against a triggering model/event, resolves the audience to linked recipients, renders the template, and creates queued messages. `midvex.notification.message._trigger_event` is the thin model-side entry point channel modules' `base.automation` server actions call, delegating straight to it.
- `midvex.notification.message.action_process`/`cron_process_pending` (on the model itself, mirroring `midvex.marketplace.sync.job` in the reference suite) delegate channel-specific delivery to the registered adapter and record the result.

## Queue-first rule

Outbound delivery always goes through a queued `midvex.notification.message` record processed by cron, except very small operations such as test connection. Never call a channel API synchronously inside the transaction that created the triggering event.

## Odoo notification dispatch

The foundry owns dispatch orchestration and must handle: recipient resolution (audience → linked recipients only), channel selection (a rule may target multiple channels; a recipient with no linked account for a channel is skipped, not errored), template rendering against the triggering record, delivery-status tracking, retry/backoff on retryable errors, and deduplication via the idempotency key so re-triggering the same event does not resend to an already-notified recipient.
