# PRD — Email Connector

## Goal

Connect the notification foundry to email delivery, reusing Odoo's own outgoing-mail infrastructure where possible.

## Functional requirements

- Configure an outgoing mail server / provider credentials per notification account.
- Test connection.
- Export rendered messages as emails to a linked recipient's address.
- Handle rate limits and retryable errors.
- Log all API operations.

## Provider-specific fields to verify

```text
smtp/API credentials, sender address, reply-to policy
```

Do not implement these blindly. Verify from the latest official docs.

## Non-goals for MVP

- HTML template design tooling;
- attachments;
- open/click tracking;
- bounce/complaint handling automation.
