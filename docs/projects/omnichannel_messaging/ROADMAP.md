# Roadmap — Omnichannel Messaging

## Provenance

Merged from `varsco_omnichannel_messaging_project/14_ROADMAP_BACKLOG.md`. Sprint-level tracking lives in `docs/SPRINT_BACKLOG.md`; this file is the phase map that backlog draws from.

This roadmap runs alongside `docs/roadmap/NOTIFICATION_ROADMAP.md`, which covers the notification suite (Email, Slack, digest, dashboards). Neither supersedes the other. Where they compete for the same next sprint, the notification roadmap's phase 6 (WhatsApp/SMS) and this roadmap's phases 1–2 are **the same work** and are being done once, in `midvex_o_notification_whatsapp`.

## Phase 0 — Discovery and contract freeze — **done**

### P0
- inspect current Notification Foundry code;
- inspect current Telegram implementation;
- inspect existing WhatsApp placeholder docs;
- inspect `varsco_content_api`;
- verify current official Meta WhatsApp Cloud API docs;
- record API versions/auth/webhook requirements;
- create architecture ADRs.

Exit:
- no duplicate Foundry concept;
- provider contract agreed.

Closed 2026-08-14 by this documentation merge and ADR-013…018.

## Phase 1 — WhatsApp notification MVP — **in progress**

### P0
- production account model;
- system-user credential strategy;
- account test connection;
- outbound approved template;
- queue/retry/log integration;
- normalized statuses.

Exit:
- Odoo event can send WhatsApp transactional notification reliably.

## Phase 2 — Inbound WhatsApp — **in progress**

### P0
- webhook;
- verification/signature;
- inbound event store;
- dedupe;
- parser;
- identity normalization;
- company resolution.

Exit:
- inbound message safely reaches a generic handler.

## Phase 3 — Conversation Foundry

### P0
- thread;
- session;
- message;
- identity;
- assignment;
- state machine;
- service methods;
- ACL/record rules;
- tests.

Exit:
- provider-neutral conversation can be created and replied to.

## Phase 4 — CRM bridge and Odoo inbox

### P0
- identity/partner matching;
- provisional contact strategy;
- lead creation;
- CRM linkage;
- inbox list;
- message view;
- reply;
- resolve/reopen;
- internal Telegram alert.

Exit:
- full first milestone works.

## Phase 5 — Website live chat

### P1
- `varsco_messaging_api`;
- session tokens;
- chat widget;
- realtime;
- offline state;
- CRM link;
- abuse controls.

Exit:
- website visitor and Odoo agent exchange messages.

The widget shell already exists as `Websites/varsco_com/src/components/layout/WhatsAppWidget.tsx`, which is currently `wa.me` deep-link only and invisible to Odoo. See ADR-016.

## Phase 6 — Web → WhatsApp handoff

### P1
- opt-in/phone validation;
- approved continuation template;
- same thread/new WhatsApp session;
- history continuity.

## Phase 7 — Mobile/PWA agent inbox

### P1
- responsive agent UI;
- installable PWA;
- push notification architecture;
- deep links.

Only required if native WhatsApp coexistence is insufficient.

## Phase 8 — AI Assist

### P1
- language detection;
- translation;
- summary;
- intent/product classification;
- reply suggestion;
- lead extraction.

## Phase 9 — Offline AI

### P2
- staffed-hour rules;
- approved auto intents;
- human takeover;
- guardrails;
- audit.

## Phase 10 — Telegram conversation

### P2
- inbound;
- thread/session mapping;
- replies;
- identity;
- tests.

## Phase 11 — Media

### P2
- images;
- PDFs;
- COA/spec documents;
- invoices/quotes;
- media retention/security.

## Phase 12 — Advanced

### P3
- team routing;
- round robin;
- SLA;
- escalations;
- analytics;
- WhatsApp Flows;
- advanced AI qualification;
- configurable channel preference center.
