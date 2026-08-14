# Data Model — Conversation Foundry

## Provenance

Merged from `varsco_omnichannel_messaging_project/05_DATA_MODEL.md`.

**Naming.** The source pack uses bare `conversation.*` model names. This repository prefixes every model with `midvex.`, matching `midvex.notification.*`. The prefixed names below are authoritative. See ADR-014.

## 1. `midvex.conversation.thread`

Canonical logical business conversation.

Suggested fields:

```text
name
company_id                 required
partner_id
lead_id
assigned_user_id
assigned_team_id
status                      new/open/waiting_customer/waiting_agent/resolved/archived
priority
language_code
first_channel_code
last_channel_code
first_response_at
last_message_at
resolved_at
ai_mode                     off/assist/auto/human_takeover
ai_summary
active
```

Indexes:
- `(company_id, status, assigned_user_id)`
- `last_message_at`
- `partner_id`
- `lead_id`

## 2. `midvex.conversation.session`

A channel-specific session attached to a logical thread.

Fields:

```text
thread_id
company_id
channel_code
account_id
external_session_id
external_recipient_id
state
opened_at
last_activity_at
closed_at
metadata_json
```

Constraint:
`account_id.company_id == company_id`

`account_id` points at the existing `midvex.notification.account` — the shared channel/account registry, not a new one.

## 3. `midvex.conversation.message`

Immutable logical message record.

Fields:

```text
thread_id
session_id
company_id
direction                   inbound/outbound/internal/system
message_type                text/template/image/document/audio/video/location/interactive/system
body
original_language
translated_body
translated_language
provider_message_id
provider_reply_to_id
reply_to_message_id
state                       queued/submitted/sent/delivered/read/failed
queued_at
sent_at
delivered_at
read_at
failed_at
error_code
error_message_safe
created_by_user_id
origin                      odoo/frontend/automation/ai/provider
generated_by_ai
ai_model_metadata
payload_fingerprint
```

Provider raw payload should not be duplicated into every message. Keep the provider envelope separately, in the inbound event.

Unique constraint where provider permits:
`(session_id, provider_message_id)`

This is deliberately a **different** model from `midvex.notification.message`. That one is a delivery queue row for an outbound alert; this one is a durable two-way conversation entry. Conflating them was the specific mistake ADR-013 exists to prevent.

## 4. `midvex.conversation.identity`

Maps Odoo people to channel identities.

Fields:

```text
company_id or company-independent policy
partner_id
identity_type               whatsapp/telegram/email/web
normalized_identifier
display_identifier
provider_identifier
verified
verification_source
first_seen_at
last_seen_at
active
```

For phone:
- canonical E.164 value;
- retain original input only if business-useful.

## 5. `midvex.conversation.inbound.event`

Immutable webhook/envelope record.

Fields:

```text
provider
account_id
company_id
external_event_id
external_message_id
payload_hash
received_at
processed_at
state                       received/processing/processed/failed/ignored
retry_count
error_code
safe_error
raw_payload_encrypted_or_restricted
correlation_id
```

Unique dedupe key:
provider + account + external event/message identifier or deterministic fingerprint.

**Relationship to `midvex.notification.inbound.event`.** The foundry already has an inbound event model, used today by the Telegram webhook and, from phase 2, by the WhatsApp webhook. Whether the conversation foundry extends that model or introduces its own is an open decision for phase 3. Extending is preferred if the dedupe key and state machine can be shared; the deciding factor is whether notification-side inbound events (command replies) and conversation-side inbound events (customer messages) genuinely want the same lifecycle. Record the outcome as an ADR before writing the model.

## 6. `midvex.conversation.assignment.event`

Audit assignment changes.

Fields:

```text
thread_id
from_user_id
to_user_id
from_team_id
to_team_id
actor_user_id
reason
created_at
```

## 7. `midvex.conversation.channel.capability`

Optional cache/registry describing channel capabilities:

```text
channel_code
supports_text
supports_templates
supports_media
supports_read_receipts
supports_typing
supports_interactive
supports_replies
```

Do not hard-code UI assumptions where a capability registry is cleaner.

## Partner extensions

Possible fields:
- preferred_channel;
- preferred_language;
- WhatsApp opt-in state;
- marketing consent;
- transactional contact permission.

Marketing consent must not be inferred from ordinary customer-service messaging.

## CRM extensions

Possible fields:
- source channel;
- product interest;
- conversation count;
- last conversation date;
- lead qualification summary;
- conversation thread links.

## Deletion/retention

Do not cascade-delete provider communication merely because a lead is deleted.
Use explicit retention/anonymization policies.
