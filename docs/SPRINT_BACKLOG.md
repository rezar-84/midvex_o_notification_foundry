# Sprint Backlog

## Sprint 0 — Governance and environment

- [x] Review product, architecture, security, and Odoo environment guidance.
- [x] Record decisions, risks, handoff process, and test runbook.
- [x] Verify Odoo service and PostgreSQL from the developer shell.

## Sprint 1 — Foundry + Telegram MVP

- [x] Install and upgrade foundry and Telegram modules in `odoo19_dev`.
- [x] Configure a company-scoped Telegram account and test connection (`getMe`) — done 2026-08-03, see `docs/HANDOFF_LOG.md`.
- [x] Link a test user's Telegram account via the `/link <code>` flow — done 2026-08-08 against `erp.varsco.com`. The tunnel prerequisite fell away rather than being met: production is itself a public HTTPS host, so `setWebhook` and inbound `/link` work there with no tunnel at all.
- [ ] Trigger a `crm.lead` creation and confirm a Telegram message is delivered — no longer blocked on a tunnel. Remaining: deploy the 2026-08-08 commits to erp, repair the live account's channel (its code is `1`, so no adapter resolves and every send fails), and set an audience on the shipped rule, which ships with none.
- [x] Demonstrate retry, redacted logs, and idempotent delivery (no duplicate sends on repeated triggers) — covered by mocked dispatch tests (`test_notification_dispatch.py`).
- [x] Complete a fresh-database Odoo test run for both modules — 0 failed, 0 error(s) of 15 tests (25 as of 2026-08-08).

## Sprint 2 — Beyond the MVP

- [x] Group-chat recipients (feature 7) — a shared chat is its own recipient `kind`, forbidden from carrying a `user_id`, and link codes are refused when redeemed in the wrong kind of chat.
- [x] Quiet hours (half of feature 8) — delivery is held and released, never dropped; windows cross midnight and are read on the recipient's own clock.
- [ ] Digest (the other half of feature 8) — batch a recipient's queued alerts into one message instead of a burst. Not started. Needs a second cron and a way to keep each event's row honest while only one message is delivered.
  Still open after the `on_schedule` work: that trigger fires **per record**, so it gives
  "this invoice is overdue" but not "here are the twelve invoices overdue this week".
- [x] Prompt delivery and rate limiting — enqueue triggers the queue cron (~2s end to end, measured),
  sends are paced inside the channel's declared limits, and a 429 no longer counts as a delivery
  failure. See ADR-012.
- [ ] Delivery dashboard (feature 9) — the foundry manifest's summary still advertises a dashboard that does not exist. Either build it or stop claiming it.
- [x] Rules wire their own `base.automation` — until 2026-08-09 a rule added in the UI matched nothing and reported no error.
- [x] Send by hand — the compose wizard, reachable from the menu, a linked recipient, and a record's Actions menu, replacing the Message Queue's dead Create button.
- [x] Ready-made business events — `midvex_o_notification_business` (CRM, Sales, Invoicing).
  Extended 2026-08-10 with eleven Accounting/Invoicing events: invoice posted, partially paid,
  due in 3 days, overdue, cancelled, customer credit note, customer payment received
  (`account.payment`, the only rule that sees deposits and unallocated payments), high-value
  invoice (ships disabled — the threshold is a placeholder), vendor bill posted, vendor bill
  paid, and vendor credit note.
- [x] Scheduled rules (`on_schedule`) — a rule can now react to a date passing rather than to
  somebody saving a record, which is what "overdue" needs. Built on `base.automation`'s
  `on_time`; see ADR-010.
- [x] Turkish translation — full `i18n/tr.po` for all three modules (353 strings, no fuzzy or
  empty entries, guarded by a test). Messages now render in the recipient's language rather
  than the acting user's; see ADR-011.
- [ ] Migrate `template_lead_created` / `rule_lead_created_telegram` out of the Telegram adapter into the business module. They are `noupdate="1"` records already installed on production, so moving the XML ids needs a migration rather than a cut and paste. Left alone deliberately.

## Sprint 3 — Email MVP

- [ ] Verify requirements against Odoo's own `mail.mail`/`ir.mail_server` before implementation.
- [ ] Implement `midvex_o_notification_email` adapter.
- [ ] Register the Email channel and pass mocked adapter unit tests.

---

# Omnichannel Messaging

Sprints 4 onward come from `docs/projects/omnichannel_messaging/ROADMAP.md`, which was
merged into this repository on 2026-08-14 (ADR-013). Nothing above is superseded: the
Email and Slack connectors and the open Sprint 2 items remain live work.

One note on sequencing. The notification roadmap's phase 6 (WhatsApp/SMS) and the
omnichannel roadmap's phases 1–2 are **the same work**, and are being done once, in
`midvex_o_notification_whatsapp`. That is why WhatsApp jumps ahead of Email and Slack.

## Sprint 4 — Contract freeze (roadmap phase 0) — done 2026-08-14

- [x] Inspect the current foundry, the Telegram implementation, the WhatsApp doc stubs and `varsco_content_api`.
- [x] Verify the current official Meta WhatsApp Cloud API documentation and record version, auth, webhook and error behavior in `docs/projects/notification_whatsapp/API_RESEARCH.md`.
- [x] Merge the specification pack into `docs/projects/`, correcting the frontend stack error.
- [x] Record ADR-013 through ADR-018.

## Sprint 5 — WhatsApp notification MVP (roadmap phase 1) — built 2026-08-14

- [x] `midvex_o_notification_whatsapp` addon: manifest, channel data, security, views, Turkish.
- [x] Account model extension — WABA ID, phone number ID, display number, API version, test mode — on the existing `midvex.notification.account`. Credentials reuse the three admin-gated fields that already exist rather than adding three more ways to leak a secret.
- [x] `services/whatsapp_client.py` — one transport client, shared with the future conversation module (ADR-017).
- [x] `services/whatsapp_adapter.py` registered on `channel_code = 'whatsapp'`.
- [x] Test connection that proves token, asset assignment and phone number ID without messaging anyone — a read of the phone number node, since there is no `getMe` equivalent.
- [x] Outbound approved-template send, and free-form text inside the window.
- [x] Semantic template → provider template mapping by account and language, looked up in the *recipient's* language (ADR-011 applies here too).
- [x] Error classification against the thirty-entry code table, with rate limits deferring rather than failing and `131047` classified permanent.
- [x] Fixture-based tests, no live API call. 76 of them.

Exit: an Odoo event can send a WhatsApp transactional notification reliably — **proven against
fixtures, never against Meta.**

- [ ] **Live validation.** Blocked on credentials, which do not exist yet. Work the eight-step
      onboarding in `docs/projects/notification_whatsapp/API_RESEARCH.md` against a dedicated
      test number, then confirm `wa_delivery_status` reaches `delivered` on a real send. That
      single value proves the outbound call, the webhook, the signature check and the status
      ladder at once.

## Sprint 6 — Inbound WhatsApp (roadmap phase 2) — built 2026-08-14

- [x] `GET` webhook verification challenge (`hub.mode` / `hub.verify_token` / `hub.challenge`).
- [x] `POST` signature validation — HMAC-SHA256 over the **raw** body, constant-time compare, 403 on mismatch or missing header, failing closed when no app secret is configured.
- [x] Store the inbound envelope before any processing; dedupe on `wa_event_key` with a unique constraint. It could not reuse `external_id` — for Telegram that column holds the chat id, and every message from one chat reuses it.
- [x] Map `statuses[]` onto queued messages as a monotonic ladder that tolerates `read` arriving before `delivered`.
- [x] Unsupported message types stored safely rather than crashing the handler.
- [x] Fast 200 acknowledgement; no business work inside the request.

Exit: an inbound message safely reaches a generic handler.

Note the bounded scope: inbound free text is **stored and acknowledged only**. Nothing threads
it, because there is no conversation model until Sprint 7. That is exactly the roadmap's phase-2
exit criterion, and the acceptance criteria doc records the same bound. It also means inbound
message events stay `processed = False` — accurately, since nothing has processed them. If a
number goes live before Sprint 7, somebody has to watch Inbound Events by hand.

## Sprint 7 — Conversation Foundry (roadmap phase 3) — built 2026-08-15

- [x] Thread, session, message, identity, assignment event — `midvex.conversation.*`.
- [x] Status lifecycle with the transitions that matter: a resolved thread reopens when the customer replies; an unclaimed one stays in the unassigned queue.
- [x] The company invariant enforced server-side on the session, which is the only record touching both the thread and the account.
- [x] Service API — adapters and bridges call it; they never `create()` on the models.
- [x] Outbound through the one delivery queue, not a second one (ADR-020).
- [x] One shared inbound envelope store (ADR-019).
- [x] ACLs and record rules extending the existing three-group ladder; history and audit append-only for everybody.
- [x] 69 tests, provider-neutral against an in-memory fake channel.
- [x] Turkish catalogue, 185 strings.

Exit: a provider-neutral conversation can be created and replied to. **Met.**

## Sprint 8 — Wire WhatsApp to it

Small, and the obvious next step. The webhook already parses inbound messages and
already stores the envelope the conversation foundry now knows how to read; what is
missing is the module that joins them.

- [ ] `midvex_o_conversation_whatsapp`: normalize inbound into the conversation DTO, call `record_inbound`, and route `statuses[]` through `apply_status`.
- [ ] The customer service window check before a free-form reply — outside 24 hours only an approved template is deliverable, and the agent needs telling before they type, not after.
- [ ] Identity normalization to E.164, reusing the adapter's `normalize_identity`.

After that, phase 4's first milestone is within reach: unknown person messages the
number, a lead is created, an agent is notified, and the reply goes back.

## Sprint 9 onward

`docs/projects/omnichannel_messaging/ROADMAP.md` phases 4–12: CRM bridge and Odoo
inbox proper, website live chat, web→WhatsApp handoff, mobile/PWA inbox, AI assist,
offline AI, Telegram conversation, media, advanced routing.

The roadmap's own rule still stands: do not start AI, media, advanced routing or
Telegram two-way work before the first WhatsApp milestone path is stable.
