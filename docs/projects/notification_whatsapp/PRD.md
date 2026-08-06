# PRD — WhatsApp Connector

## Goal

Connect the notification foundry to WhatsApp.

## Functional requirements

- Configure WhatsApp Business API credentials per notification account.
- Test connection.
- Send a rendered, pre-approved template message to a linked recipient's phone number.
- Handle rate limits and retryable errors.
- Log all API operations.

## Provider-specific fields to verify

```text
access token, phone number id, business account id, approved template names
```

Do not implement these blindly. Verify from the latest official docs.

## Non-goals for MVP

- free-form business-initiated messages (outside the 24-hour customer service window, WhatsApp requires an approved template);
- media messages;
- multi-number routing.
