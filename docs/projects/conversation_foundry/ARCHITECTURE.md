# Architecture — Conversation Foundry

## Provenance

The conversation slice of `varsco_omnichannel_messaging_project/04_ARCHITECTURE.md`. The full picture, including how the notification and conversation halves relate, is in `../omnichannel_messaging/ARCHITECTURE.md`.

## Position

```text
Channel Adapters  (whatsapp, telegram, webchat)
        |
   registry.get_adapter(channel_code)      <- shared, already exists
        |
 Conversation Foundry                       <- this module
        |
   +----+--------------+
   |                   |
 CRM bridge        Sale bridge
        |
      Odoo
        |
 Notification Foundry  -> internal alerts
```

The conversation foundry sits beside the notification foundry and depends on it — for the adapter registry, the channel/account models, and the ability to emit internal alerts. The dependency does not run the other way. Nothing in `midvex_o_notification_foundry` may import from the conversation module.

## What it owns

- conversation thread;
- channel session;
- message;
- external identity;
- assignment;
- status lifecycle;
- inbound event processing;
- a generic conversation service API;
- channel-neutral audit metadata.

## What it must not own

- provider HTTP, auth, or payload shapes;
- retry, throttle or delivery-log machinery — those exist in `midvex.notification.message` and `midvex.notification.log`;
- a second adapter registry (ADR-015);
- CRM or Sales business rules.

## Service API, not direct writes

Adapters and bridges call service methods; they do not `create()` on the models. The methods are the seam that keeps the company invariant, the state machine and the audit trail in one enforceable place. Sketch:

```text
ensure_thread(company, identity, channel_code)  -> thread
open_session(thread, account, external_ids)     -> session
record_inbound(session, normalized_inbound_dto) -> message
queue_outbound(session, normalized_outbound_dto)-> message
apply_status(provider_message_id, status)       -> message
assign(thread, user, actor, reason)             -> assignment event
resolve(thread) / reopen(thread)
```

## Inbound processing

The controller's job ends at *stored and acknowledged*. Everything after that is queued work:

```text
controller: verify -> store envelope -> dedupe -> 200 OK
queued:     adapter.parse_inbound -> ensure_thread -> record_inbound
            -> CRM matching -> notification event
```

Heavy work never runs inside the webhook request. This is not a performance preference — a slow handler makes the provider retry, and a retry that is not deduped duplicates the conversation.

## Outbound processing

Conversation outbound reuses the notification queue rather than building a second one. A queued conversation message creates the corresponding `midvex.notification.message` row, which `cron_process_pending` drains through `registry.get_adapter(channel_code).send()`, subject to the existing throttle and retry classification.

The open question for phase 3 is whether that coupling is a foreign key or an event. Decide it with an ADR before writing code; the wrong choice here is what makes the two foundries bleed into each other.

## Realtime

Odoo bus where practical; an SSE or WebSocket gateway for the headless widget; bounded long-polling as a fallback. Avoid 1–2 second constant polling. The transport is chosen after compatibility testing against the real deployment and its reverse proxy, not before.
