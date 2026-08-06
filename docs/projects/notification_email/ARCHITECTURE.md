# Architecture — Email Connector

## Module structure

```text
midvex_o_notification_email/
├── __init__.py
├── __manifest__.py
├── services/
│   ├── __init__.py
│   └── email_adapter.py
├── data/
│   └── email_channel.xml
└── tests/
    ├── __init__.py
    └── test_email_adapter.py
```

## Foundry integration

The Email adapter must implement the same adapter contract used by all channels (`test_connection`, `send`, `parse_error`; `register_webhook`/`parse_inbound` are no-ops for this channel in the MVP).

The adapter must not create Odoo records directly beyond what the foundry's dispatcher passes it.

## Adapter responsibilities

- Outgoing mail server selection/authentication (reuse Odoo's `ir.mail_server` where practical).
- Message construction (subject/body) from the rendered template.
- Response/error normalization.

Status: **planned**, not yet implemented.
