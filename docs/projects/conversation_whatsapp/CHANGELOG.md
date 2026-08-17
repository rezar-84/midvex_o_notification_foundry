# Changelog — WhatsApp Conversation Connector

## 19.0.1.0.1 — 2026-08-17

Cosmetic only. Added `static/description/icon.svg` and `icon.png`, replacing the
generic placeholder on the Apps list card. Same two-bubble glyph as the
conversation foundry with the outbound bubble in WhatsApp green — an adapter
should look like a variant of the foundry it plugs into.

No upgrade needed; the card icon is read from disk on *Update Apps List*.

## 19.0.1.0.0 — 2026-08-15

The bridge. A customer messaging a connected WhatsApp number now becomes a
conversation an agent can see and reply to.

Small on purpose — most of it already existed. The webhook verified the
signature, stored the envelope and deduped it; the adapter normalized the
payload; the conversation foundry knew how to thread one. What was missing was
the piece that joined them.

**Added**

- `process_conversation_event` override on the shared inbound event model
  (ADR-019), which is the hook `midvex_o_notification_whatsapp` calls and
  no-ops without this module installed.
- Inbound customer messages → identity → thread → session → durable message,
  with the identity normalized to E.164 through the adapter's own
  `normalize_identity`.
- Delivery statuses → the conversation message's ladder, including `failed`
  carrying the provider's own explanation.
- **The 24-hour customer service window**, enforced before an agent types
  rather than after the provider rejects the send with `131047`. The duration
  is a named constant cited from that error code, because Meta's overview names
  the window without stating how long it is.

**Two things the integration tests caught**

- **A sticker crashed the webhook.** `sticker` is not a value the conversation
  message's `message_type` Selection can hold, so the ORM refused it — and
  because Meta batches, that would have taken every message alongside it. The
  foundry now coerces any type it does not know to `other` and keeps the
  provider's own word in `provider_message_type`. Fixed in the foundry rather
  than the bridge, so every channel benefits and no channel has to remember.
- Hand-built test events prove the bridge and *assume* the seam. The tests that
  run Meta's published payloads through the real adapter and feed whatever
  comes out are the ones that found the above.

**Deliberate**

- Company resolution comes from the account the webhook matched on
  `value.metadata.phone_number_id`, never from the sender — an inbound payload
  has no `to` field, and the sender's number is the one thing an attacker
  chooses.
- Replying does not extend the window the customer opened. The window is read
  from inbound messages, not from `last_activity_at`, which moves on outbound
  too.
- A template is never refused by the window, because a template is precisely
  what is allowed outside it.
- A message with no sender is recorded `ignored`, not `failed`. Nothing is
  wrong; there is simply nobody to attribute it to.

**Still not true**

Nothing here has spoken to Meta. No credentials exist, so the whole path is
proven against sanitized fixtures and never once against the live API.

37 tests.
