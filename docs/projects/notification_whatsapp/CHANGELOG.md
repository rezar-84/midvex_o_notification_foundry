# Changelog — WhatsApp Connector

## 19.0.1.0.1 — 2026-08-14 (review pass)

Three defects found by reviewing the first commit before anything depended on it.

**Fixed — a stranger could turn a 403 into a 500.** `hmac.compare_digest` raises
`TypeError` on a `str` containing any non-ASCII character, and both comparisons
in the webhook take attacker-controlled input: the signature header, and the
`hub.verify_token` query parameter. One high byte produced an unhandled
exception instead of a refusal. That matters more than it sounds on this
endpoint, because **Meta retries a 500 and does not retry a 403** — so an
unauthenticated caller could make the endpoint noisily retryable. Both now go
through `constant_time_equals`, which encodes to bytes first and stays
constant-time.

**Fixed — a misconfigured record burned three retries and then lied.** A missing
token, a missing phone number ID or a recipient with no number were raised as
plain `UserError`, which the foundry classifies as retryable by default. Each
one retried over roughly half an hour and then reported `failed` —
indistinguishable from a provider outage, when what it needed was a person.
`WhatsAppError` now carries `permanent=True` for failures raised before the
request goes out, and those quarantine on the first attempt with
`WHATSAPP_NOT_CONFIGURED`. This is the same principle the Telegram adapter's
`_PERMANENT_FRAGMENTS` list exists to serve.

**Fixed — the template mapping model had no record rule.** Access rights say who
may read a model, not which rows. Without `rule_whatsapp_template_company`, a
user in one company could read, and a manager could edit, another company's
mappings — which name the provider templates that company had approved under
its own WABA. The acceptance criteria are explicit that a view domain is not
isolation; now there is a rule, and four tests that assert it through
`with_user` rather than trusting the declaration.

Also added: tests that drive the classification through the foundry's real
queue rather than asserting at the adapter seam, so `retryable: False` is proven
to actually reach `state = 'quarantined'`.

89 → 93 tests.

## 19.0.1.0.0 — 2026-08-14

First implementation. Outbound transactional sending and an inbound webhook for
verification and delivery status.

**Added**

- `services/whatsapp_client.py` — Cloud API transport: pinned Graph API version
  (v25.0, per-account overridable), bearer auth, request execution, and the
  provider error envelope turned into the foundry's error contract. Shared with
  the future conversation module rather than duplicated (ADR-017).
- `services/whatsapp_adapter.py` — registered on `channel_code = 'whatsapp'`.
  Implements the foundry's five methods plus the three optional conversation
  additions (`verify_webhook`, `normalize_identity`, `capabilities`) from
  ADR-015.
- `controllers/whatsapp_webhook.py` — `GET` verification challenge and `POST`
  with `X-Hub-Signature-256` HMAC-SHA256 validation over the raw body, constant
  time, failing closed when no app secret is configured.
- `midvex.notification.whatsapp.template` — semantic template to approved
  provider template, per account and language.
- Account fields: WABA ID, phone number ID, display number, API version, test
  mode. Credentials reuse the existing admin-gated `api_key`, `api_secret` and
  `webhook_secret` fields rather than adding three more ways to leak a secret.
- `midvex.notification.inbound.event.wa_event_key` — dedupe identity with a
  unique constraint. Telegram rows leave it NULL and are unaffected.
- `midvex.notification.message.wa_message_id` (stored compute over the delivery
  result) and `wa_delivery_status` (a monotonic sent → delivered → read ladder).
- 76 tests, all fixture-based. Turkish catalogue, 84 strings.

**Notable behaviour**

- **A rate limit defers; it does not fail.** Seven of Meta's numeric codes mean
  "too fast" and none of them say anything about the message. They return the
  attempt rather than consuming one, per ADR-012.
- **131047 is permanent, not retryable.** More than 24 hours since the customer
  last replied means only an approved template will be delivered. Retrying burns
  the message's remaining attempts and cannot succeed.
- **Register Webhook raises.** Meta has no `setWebhook`; the callback URL is
  configured in the App Dashboard. The button explains that instead of silently
  reporting success.
- **Statuses arrive out of order.** `read` routinely lands before `delivered`,
  so the ladder never moves backwards.

**Not included**

- Any live API call. No Meta credentials exist yet; every test uses sanitized
  fixtures, and end-to-end validation against a real number is outstanding.
- Threading inbound customer messages. They are stored, deduped and
  acknowledged, and nothing reads them — `midvex_o_conversation_foundry` does
  not exist yet. This is the roadmap's phase-2 exit criterion exactly.
- Media, interactive messages, template approval sync, multi-number routing.
