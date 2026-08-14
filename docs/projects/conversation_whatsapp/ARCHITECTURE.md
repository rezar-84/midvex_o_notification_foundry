# Architecture — WhatsApp Conversation Connector

## Provenance

The WhatsApp slice of `varsco_omnichannel_messaging_project/04_ARCHITECTURE.md` and `07_WHATSAPP_SPEC.md`.

## Owns

- WhatsApp inbound parser;
- webhook verification;
- outbound conversation payloads;
- provider error/status mapping;
- WhatsApp policy/window capabilities;
- provider message IDs;
- WhatsApp identity normalization.

## Does not own

- the HTTP client, auth header, base URL or error taxonomy — those live in `services/whatsapp_client.py` in `midvex_o_notification_whatsapp` and are imported (ADR-017);
- threading, assignment or state — `midvex_o_conversation_foundry`;
- lead creation — `midvex_o_conversation_crm`;
- the delivery queue — `midvex.notification.message`.

## Shared webhook, two consumers

```text
POST /notification/whatsapp/webhook/<account_id>
        |
   verify X-Hub-Signature-256 (raw body, HMAC-SHA256, constant time)
        |
   store midvex.notification.inbound.event   <- before anything else
        |
   dedupe on (account, external message id)
        |
   200 OK                                     <- fast, always
        |
   queued: adapter.parse_inbound(raw)
        |
   +----------------------+----------------------+
   |                      |                      |
 statuses[]           messages[]            everything else
   |                      |                      |
 update delivery      conversation          store and ignore,
 state on the         foundry               safely
 notification queue
```

The `statuses[]` branch is phase 2 and needs no conversation model. The `messages[]` branch is phase 3 and cannot be built before it. That is why the endpoint ships first with the right branch inert.

## Identity normalization

WhatsApp identifies a person by a phone number in a provider-specific form. Normalize to canonical E.164 on the way in, and match `midvex.conversation.identity` on that value alone. Store the provider's raw form separately — it is useful for debugging and useless for matching.

Never match on a display name.

## Messaging window

The customer-service window governs whether a free-form reply is allowed or a pre-approved template is required. The window is a property of the *session*, computed from the last inbound customer message, and its duration is a provider policy value that changes — read it from `API_RESEARCH.md`, do not hard-code it in a constant with no citation.

The check belongs in the adapter, before the send, and its result belongs in the UI, before the agent types.

## Message ordering

Delivery statuses arrive out of order in practice: `read` can land before `delivered`. Model state as a monotonic ladder (`queued < submitted < sent < delivered < read`, with `failed` terminal) and refuse to move backwards, rather than assuming arrival order matches reality.
