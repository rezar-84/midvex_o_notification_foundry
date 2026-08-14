# Project Brief — VARS Omnichannel Messaging

## Provenance

Merged from `varsco_omnichannel_messaging_project/01_PROJECT_BRIEF.md` (drop dated 2026-08-14). See `docs/projects/notification_foundry/DECISIONS.md` ADR-013.

## Background

VARS operates a headless Odoo architecture. Odoo 19 contains core business data while the public website is a separate application that calls custom Odoo APIs.

The company already developed a reusable Notification Foundry and a Telegram channel adapter. Website leads can trigger Telegram notifications. The next requirement is to add reliable WhatsApp communication, website live chat, and eventually two-way Telegram conversations.

The business currently has a small sales team, but the architecture must support future assignment, delegation, multilingual traffic, multiple companies, multiple brands, multiple WhatsApp numbers, and AI assistance.

> **Correction on merge.** The source pack states throughout that the public website is a Next.js application. It is not. `Websites/varsco_com` is TanStack Start + Vite + React on Bun, Lovable-synced. Every passage below reads "the frontend" rather than "Next.js". See ADR-016.

## Business problem

Customer communication is fragmented across:

- website forms;
- phone;
- WhatsApp;
- Telegram notifications;
- future live chat.

The company needs one customer communication history linked to Odoo CRM and sales data without making channel applications themselves the source of truth.

## Vision

Build a reusable, multi-company communication platform inside Odoo that lets customers choose their preferred communication channel while employees work from one consistent conversation/CRM workflow.

## Primary goals

- Add official WhatsApp messaging to Odoo.
- Support separate branded WhatsApp accounts/numbers per Odoo company.
- Send transactional notifications to customers and partners.
- Receive inbound WhatsApp messages.
- Automatically identify contacts and create CRM leads when appropriate.
- Provide an Odoo agent inbox.
- Provide a frontend live-chat widget.
- Preserve one logical conversation across web chat and WhatsApp where possible.
- Reuse Notification Foundry queues, account abstraction, logging, templates, and retry.
- Add multilingual AI assistance after the human messaging foundation is stable.
- Support future routing/assignment without forcing complexity into the MVP.

## Success criteria

The system is successful when:

- sales messages are not lost;
- incoming WhatsApp conversations automatically reach Odoo;
- agents do not need Meta Business Manager for daily messaging;
- customer/lead context is immediately visible;
- company identities cannot cross accidentally;
- messaging failures are observable and retryable;
- staff can respond from mobile through a reliable Odoo/PWA interface if WhatsApp Business App coexistence is unavailable;
- new channels can be added with an adapter instead of duplicating infrastructure.

## Out of scope for MVP

- marketing broadcast campaigns;
- mass unsolicited messaging;
- complex omnichannel contact-center workforce management;
- voice calling;
- attachment-heavy workflows;
- advanced WhatsApp Flows;
- sentiment-driven automated sales decisions;
- fully autonomous quoting or pricing;
- cross-company shared customer inbox without explicit permissions.

## Stakeholders

- Sales
- Management
- Odoo development team
- Frontend development team
- Marketing/CRM operations
- Future support/customer-service agents

## Constraints

- Odoo 19.
- Odoo is multi-company.
- Existing Foundry must remain backward compatible.
- Existing Telegram notifications must not regress.
- Headless frontend.
- No provider secret may reach browser JavaScript.
- Official provider rules and APIs can change; implementation must verify current docs before coding.
