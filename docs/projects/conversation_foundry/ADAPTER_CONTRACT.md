# Adapter Contract — Conversation Foundry

## Provenance

Merged from `varsco_omnichannel_messaging_project/06_ADAPTER_CONTRACT.md`, reconciled against the contract already in force at `../notification_foundry/ADAPTER_CONTRACT.md`.

## Objective

All providers expose different APIs. Conversation Foundry consumes normalized DTOs so business logic never depends on Meta or Telegram payload shape.

## One registry, not two

The source pack proposes a `ConversationChannelAdapter` class with seven methods. This repository **already has** an adapter registry at `addons/midvex_o_notification_foundry/services/registry.py` (`register_adapter` / `get_adapter` / `available_adapter_codes` / `unregister_adapter`), keyed on `channel_code`, and a five-method contract that `TelegramAdapter` implements today.

The pack itself says: *"Names may follow existing Foundry conventions; do not invent an incompatible registry when reuse is possible."* Reuse is possible. See ADR-015.

The reconciled contract is therefore **the existing five methods, plus three additions** — one adapter class per `channel_code`, serving both notification and conversation callers:

```python
@register_adapter
class SomeAdapter:
    channel_code = 'whatsapp'

    # --- existing contract, unchanged ---
    def test_connection(self, account): ...
    def send(self, account, message_dto): ...
    def register_webhook(self, account, webhook_url, secret_token): ...
    def parse_inbound(self, raw_payload): ...
    def parse_error(self, response_or_exception): ...

    # --- conversation additions ---
    def verify_webhook(self, request, account): ...
    def normalize_identity(self, raw_identifier): ...
    def capabilities(self, account=None): ...
```

Mapping from the pack's proposed names:

| Pack name | Reconciled to |
|---|---|
| `validate_account` | `test_connection` (already exists, same job) |
| `verify_webhook` | new — Telegram does this inline in its controller today; lifting it into the adapter is the correct move |
| `parse_inbound(request, account)` | `parse_inbound(raw_payload)` — existing signature kept; account context is the controller's job |
| `send_message` | `send` (already exists) |
| `normalize_status_event` | folded into `parse_inbound`, which returns an event whose type distinguishes a message from a status |
| `normalize_identity` | new |
| `capabilities` | new |

An adapter that implements only the five existing methods stays valid. The three additions are optional and default to conservative behavior: no verification, identity returned unchanged, text-only capabilities.

## Normalized inbound DTO

The conversation-side inbound envelope, richer than the notification-side one:

```text
provider
channel_code
account_external_id
external_event_id
external_message_id
sender_identifier
recipient_identifier
timestamp
message_type
body
reply_to_external_id
language_hint
attachments[]
raw_metadata_minimal
```

## Normalized outbound DTO

```text
channel_code
account_id
recipient_identifier
message_type
body
template_key
template_variables
reply_to_external_id
attachments[]
business_record_reference
correlation_id
```

## Normalized delivery result

```text
accepted
provider_message_id
provider_status
normalized_status
retryable
rate_limit_reset
error_code
safe_error_message
provider_request_id
```

This is a superset of the existing delivery-result DTO. `retryable`, `error_code` and `rate_limit_reset` already exist in the foundry's error contract under the names `retryable`, `error_code` and `retry_after_seconds`; keep those names rather than introducing synonyms.

## Error taxonomy

Shared error classes:

- authentication;
- permission;
- validation;
- recipient_invalid;
- template_invalid;
- policy_restricted;
- rate_limited;
- provider_unavailable;
- network_timeout;
- duplicate;
- unknown.

Adapter must mark retryable vs permanent.

A rate limit is **not** a delivery failure. It defers and returns the attempt; it does not consume a retry. That was learned the hard way — see ADR-012 and the 2026-08-09 handoff entry.

## Rules

- Adapter does not create CRM leads.
- Adapter does not assign sales users.
- Adapter does not bypass company record rules.
- Adapter does not write delivery logs outside shared Foundry hooks unless explicitly delegated.
- Adapter never logs secrets.
- Adapter verification must happen before business processing.
- Provider payload parsing must be covered by fixture-based tests.
