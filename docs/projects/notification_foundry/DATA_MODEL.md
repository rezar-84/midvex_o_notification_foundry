# Data Model — Notification Foundry

## `midvex.notification.channel`

Catalog row per channel type, registered by the channel module that implements it.

Fields:

```text
name
code
active
module_name
supports_inbound
documentation_url
```

## `midvex.notification.account`

Represents one channel account/credential set for one company.

Fields:

```text
name
channel_id
channel_code
company_id
active
state
credential_json
webhook_url
webhook_secret
last_test_at
last_error
```

States: `draft`, `connected`, `error`. Credentials must be stored securely and masked in views/logs.

## `midvex.notification.recipient`

Links an Odoo user to a channel identity.

Fields:

```text
user_id
account_id
channel_code
external_id
external_username
state
link_code
link_code_expires_at
linked_at
active
```

States: `pending`, `linked`, `revoked`.

## `midvex.notification.template`

Fields:

```text
name
code
model_id
subject
body
active
```

## `midvex.notification.rule`

Fields:

```text
name
model_id
trigger
trigger_domain
template_id
channel_ids
audience_group_ids
audience_user_ids
company_id
active
```

Triggers: `on_create`, `on_write`.

## `midvex.notification.message`

Fields:

```text
name
rule_id
recipient_id
account_id
channel_code
res_model
res_id
subject
body
state
idempotency_key
attempt_count
max_attempts
next_retry_at
payload_json
result_json
error_code
error_message
created_at
sent_at
```

States: `pending`, `sending`, `sent`, `failed`, `quarantined`.

## `midvex.notification.log`

Fields:

```text
message_id
channel_code
status
request_reference
external_reference
message
error_code
error_details
duration_ms
metadata_json
create_date
```

## `midvex.notification.inbound.event`

Fields:

```text
channel_id
account_id
event_type
external_id
raw_payload
processed
processed_at
recipient_id
error_message
create_date
```

## Duplicate-prevention rules

Unique constraints prevent duplicates for channel code, for account plus recipient external id, and for message idempotency key (derived from rule + record + recipient + channel).

## Multi-company rule

Every notification operational model must include `company_id` (directly, or `related=..., store=True` where scoped through a parent record).
