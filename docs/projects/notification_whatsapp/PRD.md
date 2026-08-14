# PRD — WhatsApp Notification Connector

## Goal

Connect the notification foundry to WhatsApp, so an Odoo business event can reliably reach a customer's phone.

## Functional requirements

- Configure WhatsApp Cloud API credentials per notification account, scoped to one Odoo company.
- Test connection without messaging anyone.
- Send a rendered, pre-approved template message to a recipient's phone number.
- Send free-form text inside the 24-hour customer service window.
- Map semantic templates to provider templates by company and language.
- Handle rate limits and retryable errors, distinguishing them from permanent failures.
- Receive delivery and read status webhooks and reflect them on the queued message.
- Log all API operations, without bodies or credentials.

## Provider-specific fields

Verified 2026-08-14 — see `API_RESEARCH.md` for citations:

```text
access token (System User, scopes: business_management,
              whatsapp_business_messaging, whatsapp_business_management)
phone number id
WhatsApp Business Account (WABA) id
display phone number
app secret            (webhook signature key)
webhook verify token
Graph API version     (pinned v25.0; latest is v26.0)
approved template names, by language-and-locale code
```

Production must not use a temporary dashboard token. Meta's own guide calls it unsuitable.

## Non-goals for MVP

- free-form business-initiated messages outside the 24-hour window — the provider rejects them with error `131047`, and the answer is an approved template, not a retry;
- media messages;
- interactive messages, buttons, location, Flows;
- multi-number routing within one company;
- template approval status sync — manual provider template identifiers are acceptable, and the sync is only worth building if the manual list becomes a maintenance burden;
- threading inbound customer messages into conversations — a different module (`../conversation_whatsapp/`) and a different phase.

## Acceptance

From `../omnichannel_messaging/ACCEPTANCE_CRITERIA.md`:

- company-specific account selected correctly;
- test connection returns a safe diagnostic;
- message queues asynchronously;
- retryable failures retry;
- permanent failures stop retrying;
- provider message ID stored;
- delivery/read state maps correctly;
- wrong-company send is denied.

Plus, for the webhook:

- forged webhook rejected;
- valid webhook acknowledged;
- duplicate delivery does not duplicate records;
- company resolved from the destination account;
- unsupported payload does not crash the handler.

## What cannot be accepted without credentials

No Meta credentials exist yet. Everything above is provable against sanitized fixtures except a real end-to-end delivery, which stays an explicit outstanding step — the same step that is still open for Telegram, where a rule-triggered delivery has never once been observed against the live API.
