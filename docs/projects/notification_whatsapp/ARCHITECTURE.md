# Architecture — WhatsApp Connector

## Module structure

```text
midvex_o_notification_whatsapp/
├── __init__.py
├── __manifest__.py
├── services/
│   ├── __init__.py
│   └── whatsapp_adapter.py
├── data/
│   └── whatsapp_channel.xml
└── tests/
    ├── __init__.py
    └── test_whatsapp_adapter.py
```

## Foundry integration

The WhatsApp adapter must implement the same adapter contract used by all channels.

The adapter must not create Odoo records directly beyond what the foundry's dispatcher passes it.

Status: **planned**, not yet implemented.
