# Requirements — Omnichannel Messaging

## Provenance

Merged from `varsco_omnichannel_messaging_project/03_REQUIREMENTS.md`.

## Functional requirements

### FR-001 Channel account management
System shall support multiple channel accounts for the same provider and map each account to an Odoo company.

### FR-002 WhatsApp outbound
System shall send approved WhatsApp messages using the configured official provider integration.

### FR-003 WhatsApp inbound
System shall receive WhatsApp webhook events and convert them to normalized inbound events.

### FR-004 Delivery state
System shall map provider-specific states into normalized message states.

### FR-005 Contact identity
System shall normalize phone numbers to E.164 and map them to channel identities.

### FR-006 CRM lead creation
System shall create a CRM lead when an unknown sales enquiry meets configured criteria.

### FR-007 Duplicate prevention
Repeated webhook delivery shall not duplicate messages, leads, contacts, or notifications.

### FR-008 Conversation inbox
Authorized Odoo users shall view, filter, assign, reply to, resolve, and reopen conversations.

### FR-009 Live chat
The frontend shall provide a headless chat widget backed by authenticated/controlled Odoo APIs.

### FR-010 Realtime updates
Agent and web-chat interfaces shall receive new messages without high-frequency polling.

### FR-011 Internal notification
Conversation events shall be capable of triggering Notification Foundry rules.

### FR-012 Multi-company
All conversations, sessions, identities, templates, and channel accounts shall be safely scoped.

### FR-013 Message window/template enforcement
WhatsApp adapter shall prevent unsupported message types based on provider policy/state and require an approved template where necessary.

### FR-014 Language
System shall store original message language and optionally translated text without overwriting the original.

### FR-015 AI assist
AI may suggest replies, summarize, translate, classify intent, and extract lead fields.

### FR-016 AI auto mode
AI automatic reply must be explicitly enabled by company/channel/rule and must support human takeover.

### FR-017 Audit
System shall record actor, channel, company, origin UI/API, and AI involvement for outbound customer messages.

### FR-018 Webhook replay
Administrators shall be able to inspect failed events and safely replay processing.

### FR-019 Template mapping
Internal semantic templates shall map to provider-specific templates by channel/company/language.

### FR-020 Mobile
Inbox must be usable from mobile browser/PWA. Ordinary WhatsApp Business App coexistence is optional, not a required dependency.

## Non-functional requirements

### NFR-001 Reliability
No customer message should be lost silently.

### NFR-002 Idempotency
Webhook and queued processing must tolerate retries.

### NFR-003 Performance
Webhook acknowledgement path must be fast and defer heavy processing.

### NFR-004 Security
Provider credentials must be server-side only and protected from logs/UI exposure.

### NFR-005 Observability
Every failed send/receive operation must have structured error state and correlation identifiers.

### NFR-006 Testability
Provider HTTP calls must be mockable.

### NFR-007 Extensibility
Adding a provider must not require implementing new retry, audit, permission, or base queue systems.

### NFR-008 Backward compatibility
Existing Telegram notifications continue working through the existing Foundry contract.

### NFR-009 Privacy
Logs must avoid storing unnecessary full message bodies or secrets.

### NFR-010 Maintainability
Channel-specific payload details stay out of shared business models.

## Constraints

- Odoo 19 patterns only.
- No edits to Odoo Community/Enterprise core.
- Modules live under `addons/`, symlinked into the local custom addons directory.
- Use local developer run/test instructions from `~/Development/odoo19-dev/AGENTS.md`.
- Provider API details must be confirmed from official documentation at implementation time.

## Coverage in the current phase

| Requirement | Status |
|---|---|
| FR-001, FR-002, FR-004, FR-019 | Being built in `midvex_o_notification_whatsapp` |
| FR-003, FR-007, NFR-002 | Being built as the WhatsApp inbound webhook |
| NFR-004, NFR-006, NFR-008, NFR-009 | Inherited from the existing foundry, re-tested |
| FR-005, FR-006, FR-008, FR-009…FR-018, FR-020 | Not started — require Conversation Foundry (phase 3+) |
