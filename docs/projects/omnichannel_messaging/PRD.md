# Product Requirements — Omnichannel Messaging

## Provenance

Merged from `varsco_omnichannel_messaging_project/02_PRD.md`.

## Product name

Omnichannel Messaging & Conversation Foundry

## User personas

### Sales Agent
Needs to:
- see new conversations quickly;
- identify who is contacting the business;
- reply through WhatsApp or web chat;
- access CRM/contact/order context;
- create or open a quotation;
- transfer a conversation later;
- work from mobile.

### Sales Supervisor
Needs to:
- see unassigned/open/waiting conversations;
- reassign work;
- review response times;
- inspect failures and escalations.

### Administrator
Needs to:
- configure channel accounts per company;
- test connectivity;
- configure templates;
- inspect provider health;
- manage access rights;
- rotate/revoke credentials.

### Customer
Needs to:
- contact the correct branded business;
- receive prompt acknowledgement;
- continue communication through preferred channels;
- avoid repeatedly providing the same details.

## Core user journeys

### Journey A — New WhatsApp lead

Customer sends a WhatsApp message.

System:
1. receives and validates webhook;
2. identifies destination WhatsApp account;
3. resolves company;
4. normalizes sender identity;
5. finds partner/lead;
6. creates a conversation;
7. creates CRM lead if required;
8. sends internal notification;
9. agent replies;
10. provider delivery/read status updates Odoo.

### Journey B — Existing customer WhatsApp

Customer phone already maps to a partner.

System:
- attaches conversation to existing partner;
- shows CRM/orders/quotes;
- does not create duplicate partner;
- optionally creates a new opportunity based on classification rules.

### Journey C — Live chat lead

Visitor opens website chat and enters minimum required identity information.

System:
- creates chat session;
- creates/links conversation;
- starts realtime messaging;
- links CRM lead if required;
- allows handoff to WhatsApp.

### Journey D — Transactional WhatsApp notification

Odoo event occurs, such as quotation created.

Notification Foundry:
- selects approved template;
- selects company WhatsApp account;
- queues delivery;
- sends asynchronously;
- stores delivery state;
- links message back to business record.

This is the only journey in scope for the current phase, and it is the one the existing foundry already serves for Telegram.

### Journey E — Offline multilingual customer

Customer contacts business outside staffed hours in a non-primary language.

AI:
- detects language;
- provides approved FAQ/product guidance;
- collects qualification fields;
- creates/updates lead;
- summarizes conversation;
- hands off to human.

AI must not autonomously negotiate pricing or create binding commercial commitments.

## Product principles

- Odoo is canonical.
- One customer can have many channel identities.
- One logical conversation can have many channel sessions.
- Provider messages are immutable event records; business metadata may evolve.
- Inbound processing is idempotent.
- Human takeover is always available.
- Company isolation is mandatory.
- AI is optional and subordinate to business rules.
