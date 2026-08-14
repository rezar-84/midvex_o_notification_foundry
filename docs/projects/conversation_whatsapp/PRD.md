# PRD — WhatsApp Conversation Connector

## Provenance

Merged from `varsco_omnichannel_messaging_project/07_WHATSAPP_SPEC.md`. The parts of that spec that concern outbound transactional notification live in `../notification_whatsapp/`; this file keeps the two-way half.

## Provider strategy

Default implementation target: official Meta WhatsApp Cloud API directly.

A third-party BSP must remain pluggable, but is not required for MVP.

## Account model

Each company should normally have a separate branded WhatsApp number/account.

Required account fields are provider-version dependent and must be verified from current official Meta documentation before implementation. Likely configuration includes:

- company;
- WABA/business account identifier;
- phone number identifier;
- display number;
- access credential reference;
- app/webhook secret reference;
- webhook verification token/reference;
- API version;
- enabled;
- test mode.

These extend the existing `midvex.notification.account`; they do not create a second account model.

## Authentication

Production must not depend on temporary developer-dashboard tokens.

Implementation must document:
- current supported production authentication flow;
- system-user/business asset assignment;
- permissions/scopes;
- token lifetime/rotation behavior;
- revocation procedure.

Never write production token values into docs.

## Phone/mobile coexistence

Do not assume an API-connected number remains usable in the ordinary WhatsApp Business mobile app.

Before migrating any important production number:
1. test with a dedicated number;
2. verify whether Meta currently supports a supported coexistence path for that exact onboarding/account type;
3. document limitations;
4. ensure PWA/Odoo mobile inbox is operational as fallback.

## Inbound webhook requirements

Must support:
- verification challenge where applicable;
- signature validation;
- text messages;
- delivery/read/status events;
- unsupported message types recorded safely;
- deduplication;
- replay protection;
- company resolution from destination account/phone context.

## Outbound requirements

MVP:
- text/session replies where policy permits;
- approved template messages;
- locale/template mapping;
- delivery tracking;
- retry classification.

Later:
- image/document;
- interactive messages;
- location;
- buttons;
- Flows.

## Customer service messaging policy

The adapter must provide a policy/capability check before send.

Conceptual service:

```text
can_send_freeform(session, now) -> bool
required_template_type(...)
```

Do not hard-code mutable provider policy values without official verification and documentation.

This check is what makes the two-way module more than a thin wrapper: outside the customer-service window, a free-form reply is rejected by the provider, and the agent needs to be told that before they type, not after.

## Template abstraction

Odoo semantic template:
`quotation_sent`

Provider mappings:
- company;
- language;
- provider template name/id;
- provider category;
- provider status;
- variables schema;
- last sync time.

Sync is optional; manual provider template identifiers are acceptable for MVP.

## Delivery statuses

Map provider-specific states into:
- queued;
- submitted;
- sent;
- delivered;
- read;
- failed.

Raw provider state may also be retained.

## Phone normalization

Use a proven phone parsing library or Odoo-supported phone normalization where appropriate.
Store canonical E.164 for matching.

## Initial templates

Recommended transactional templates:
- enquiry acknowledgement;
- quotation ready;
- order confirmation;
- payment reminder/receipt where appropriate;
- shipment update;
- follow-up request;
- conversation continuation from web chat.

Template copy/content approval is a business task, not hard-coded into transport code.

## Initial acceptance test

Unknown customer sends a WhatsApp text to the company number:
- validated webhook;
- company resolved;
- identity created;
- lead created;
- agent notified;
- reply sent;
- delivered/read statuses reflected.
