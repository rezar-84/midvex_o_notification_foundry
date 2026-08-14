# Acceptance Criteria and Definition of Done — Omnichannel Messaging

## Provenance

Merged from `varsco_omnichannel_messaging_project/16_ACCEPTANCE_CRITERIA.md`. This extends, and does not replace, the eleven-gate Definition of Done in the root `AGENTS.md`.

## Epic-level Definition of Done

A feature is done only when:
- install works;
- upgrade works;
- access rights exist;
- record rules exist;
- multi-company tested;
- failure behavior tested;
- docs updated;
- no secrets exposed;
- audit/log behavior defined;
- backward compatibility considered.

## WhatsApp outbound acceptance

- company-specific account selected correctly;
- test connection returns safe diagnostic;
- message queues asynchronously;
- retryable failures retry;
- permanent failures stop retrying;
- provider message ID stored;
- delivery/read state maps correctly;
- wrong-company send is denied.

## WhatsApp inbound acceptance

- forged webhook rejected;
- valid webhook acknowledged;
- duplicate delivery does not duplicate records;
- company resolved from destination account;
- identity normalized;
- conversation created/updated;
- CRM rules run asynchronously/safely;
- unsupported payload does not crash handler.

> In the current phase, "conversation created/updated" and "CRM rules run" are **not** achievable — there is no conversation model yet. Phase 2's acceptance is bounded to: forged rejected, valid acknowledged, duplicates deduped, company resolved, identity normalized, unsupported payload survives.

## Conversation Foundry acceptance

- one thread can contain multiple sessions;
- one session belongs to one company/account;
- inbound/outbound messages ordered consistently;
- resolve/reopen lifecycle works;
- assignment audited;
- cross-company access denied.

## CRM acceptance

- known partner linked;
- unknown lead created only under configured rule;
- duplicates reduced;
- source/channel stored;
- thread accessible from CRM;
- important conversation activity summarized into CRM without flooding chatter.

## Live chat acceptance

- identified visitor can start;
- opaque token protects history;
- message reaches Odoo;
- agent reply reaches browser;
- refresh/reconnect works;
- abuse rate limit works;
- WhatsApp continuation can attach to same thread.

## AI acceptance

- AI off truly disables automation;
- assist never sends automatically;
- auto only handles allowed intents;
- human takeover stops auto replies;
- original text retained;
- source-of-truth data comes from approved tools/data;
- commercial commitments require human workflow.

## Production readiness

- staging test number validated;
- production credential rotation documented;
- monitoring/alerts configured;
- rollback steps documented;
- existing Telegram notifications regression-tested.

Two prerequisites are known-unverified on `erp.varsco.com` and block *all* delivery, WhatsApp included: a cron worker must be running (`max_cron_threads = 0` means nothing ever sends, triggered or not), and the live Telegram account's channel code was recorded as `1` rather than `telegram`, which makes `get_adapter()` fail on every send. See the 2026-08-10 entry in `docs/HANDOFF_LOG.md`.
