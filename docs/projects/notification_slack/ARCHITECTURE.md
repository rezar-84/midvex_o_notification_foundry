# Architecture — Slack Connector

## Module structure

```text
midvex_o_notification_slack/
├── __init__.py
├── __manifest__.py
├── services/
│   ├── __init__.py
│   └── slack_adapter.py
├── data/
│   └── slack_channel.xml
└── tests/
    ├── __init__.py
    └── test_slack_adapter.py
```

## Foundry integration

The Slack adapter must implement the same adapter contract used by all channels.

The adapter must not create Odoo records directly beyond what the foundry's dispatcher passes it.

Status: **planned**, not yet implemented.
