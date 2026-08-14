# API Research — WhatsApp Cloud API

This file satisfies the `AGENTS.md` channel API docs rule. It is shared by both WhatsApp projects: `notification_whatsapp` (outbound transactional) and `conversation_whatsapp` (two-way). `../conversation_whatsapp/API_RESEARCH.md` points here rather than duplicating it.

## Documentation checked

- **URLs:**
  - `https://developers.facebook.com/docs/whatsapp/cloud-api/` (overview, limits)
  - `https://developers.facebook.com/docs/whatsapp/cloud-api/guides/send-messages/` (messages endpoint)
  - `https://developers.facebook.com/docs/whatsapp/cloud-api/webhooks/payload-examples` (webhook payloads)
  - `https://developers.facebook.com/docs/graph-api/webhooks/getting-started` (verification and signature)
  - `https://developers.facebook.com/documentation/business-messaging/whatsapp/get-started` (credentials)
  - `https://developers.facebook.com/documentation/business-messaging/whatsapp/support/error-codes` (error codes)
  - `https://developers.facebook.com/docs/graph-api/changelog` (versions)
- **Date checked:** 2026-08-14
- **Latest Graph API version:** **v26.0**, released 2026-07-29. v25.0 (2026-02-18) is available until 2028-07-29; v24.0 (2025-10-08) until 2028-02-18.
- **Version to pin:** `v25.0`. It is one behind latest, has a documented two-year runway, and the send/webhook shapes below were read against it. The version is a **per-account configuration field**, not a constant, so moving to v26.0 is a data change and not a code release.
- **Base URL:** `https://graph.facebook.com/<version>`
- **Authentication method:** `Authorization: Bearer <ACCESS_TOKEN>`
- **Required headers:** `Authorization`, `Content-Type: application/json`

## Credentials

Production **must not** use the temporary dashboard token — Meta's own guide calls it unsuitable, saying it "expires quickly." Production uses a **System User access token**:

1. Business Settings → create a system user.
2. Assign the WhatsApp Business Account and the app as assets to that system user.
3. Generate a token with these three permissions:
   - `business_management`
   - `whatsapp_business_messaging`
   - `whatsapp_business_management`

**Token lifetime:** Meta's get-started guide does not state an explicit lifetime for system-user tokens beyond calling them permanent. Treat that as *unverified* and plan for rotation regardless — build the rotation path before the first production send, not after the first outage.

**Identifiers to capture** (both from the App Dashboard's API Setup panel):
- WhatsApp Business Account ID (WABA ID)
- Business phone number ID

**Revocation:** removing the system user's asset assignment, or deleting the system user, invalidates the token. Confirm the exact current procedure at rotation time.

**Never** record token values in this file, in `docs/`, in test fixtures, or in a handoff entry.

## Send endpoint

```text
POST https://graph.facebook.com/<version>/<PHONE_NUMBER_ID>/messages
Authorization: Bearer <ACCESS_TOKEN>
Content-Type: application/json
```

### Plain text

```json
{
  "messaging_product": "whatsapp",
  "recipient_type": "individual",
  "to": "+16505551234",
  "type": "text",
  "text": {
    "preview_url": true,
    "body": "Your message content here"
  }
}
```

### Approved template

```json
{
  "messaging_product": "whatsapp",
  "recipient_type": "individual",
  "to": "PHONE_NUMBER",
  "type": "template",
  "template": {
    "name": "TEMPLATE_NAME",
    "language": { "code": "LANGUAGE_AND_LOCALE_CODE" },
    "components": [
      {
        "type": "body",
        "parameters": [
          { "type": "text", "text": "parameter_value" }
        ]
      }
    ]
  }
}
```

Language codes are language-and-locale, e.g. `en_US`, `tr_TR`. This maps onto the foundry's existing render-in-the-recipient's-language behavior (ADR-011), but the provider template is selected by code — a template approved in `en_US` cannot be sent as `tr_TR`.

### Success response

```json
{
  "messaging_product": "whatsapp",
  "contacts": [
    { "input": "+16505551234", "wa_id": "16505551234" }
  ],
  "messages": [
    { "id": "wamid.HBgLMTY0NjcwNDM1OTUVAgARGBI4MjZGRDA0OUE2OTQ3RkEyMzcA" }
  ]
}
```

The provider message ID is `messages[0].id`, prefixed `wamid.`. Store it; every subsequent status event references it and nothing else.

## Test connection

There is no `getMe` equivalent. Use a `GET` on the phone number node:

```text
GET https://graph.facebook.com/<version>/<PHONE_NUMBER_ID>
```

A 200 with the node's fields proves token validity, asset assignment and phone-number-ID correctness in one call, without sending a message to anyone. *Unverified against the docs read above* — confirm the exact readable fields before relying on the response body for anything more than a boolean.

## Webhooks

### Verification (GET)

Meta sends three query parameters:

| Parameter | Value |
|---|---|
| `hub.mode` | always `subscribe` |
| `hub.challenge` | an `int` that must be echoed back |
| `hub.verify_token` | the string configured in the App Dashboard's Verify Token field |

Compare `hub.verify_token` against the account's configured token; if it matches, respond with the raw `hub.challenge` value as the body.

### Payload validation (POST)

- **Header:** `X-Hub-Signature-256`
- **Format:** the value is prefixed `sha256=`; everything after that prefix is the hex digest
- **Algorithm:** HMAC-SHA256
- **Key:** the **app secret**
- **Payload:** the complete, unmodified event notification body

Compute over the **raw** bytes. Re-serializing parsed JSON changes whitespace and key order and will never match. Compare in constant time. Reject with 403 on mismatch or a missing header.

Respond `200 OK` to all event notifications, including ones you ignore. A non-200 makes Meta retry, and a retry that is not deduped duplicates the conversation.

### Inbound message notification

```json
{
  "object": "whatsapp_business_account",
  "entry": [
    {
      "id": "102290129340398",
      "changes": [
        {
          "value": {
            "messaging_product": "whatsapp",
            "metadata": {
              "display_phone_number": "15550783881",
              "phone_number_id": "106540352242922"
            },
            "contacts": [
              { "profile": { "name": "Sheena Nelson" }, "wa_id": "16505551234" }
            ],
            "messages": [
              {
                "from": "16505551234",
                "id": "wamid.HBgLMTY1MDM4Nzk0MzkVAgASGBQzQTRBNjU5OUFFRTAzODEwMTQ0RgA=",
                "timestamp": "1749416383",
                "type": "text",
                "text": { "body": "Does it come in another color?" }
              }
            ]
          },
          "field": "messages"
        }
      ]
    }
  ]
}
```

`entry[].id` is the WABA ID. `value.metadata.phone_number_id` is the destination business number — **this is what resolves the Odoo company**, not the `to` field, which does not appear in inbound payloads.

### Status notification

```json
{
  "object": "whatsapp_business_account",
  "entry": [
    {
      "id": "102290129340398",
      "changes": [
        {
          "value": {
            "messaging_product": "whatsapp",
            "metadata": {
              "display_phone_number": "15550783881",
              "phone_number_id": "106540352242922"
            },
            "statuses": [
              {
                "id": "wamid.HBgLMTY1MDM4Nzk0MzkVAgARGBI3MTE5MjVBOTE3MDk5QUVFM0YA",
                "status": "delivered",
                "timestamp": "1750263773",
                "recipient_id": "16505551234",
                "conversation": {
                  "id": "6ceb9d929c9bdc4f90e967a32f8639b4",
                  "origin": { "type": "service" }
                },
                "pricing": {
                  "billable": true,
                  "pricing_model": "CBP",
                  "category": "service"
                }
              }
            ]
          },
          "field": "messages"
        }
      ]
    }
  ]
}
```

Both message and status notifications arrive under `field: "messages"`. The branch is on which key is present in `value` — `messages` or `statuses` — not on the field name.

## Status mapping

| Provider `status` | Foundry state |
|---|---|
| *(202 accepted at send)* | `submitted` |
| `sent` | `sent` |
| `delivered` | `delivered` |
| `read` | `read` |
| `failed` | `failed` |

Treat these as a monotonic ladder. `read` arriving before `delivered` is normal, not an anomaly; never move a message backwards down the ladder.

## Error format

```json
{
  "error": {
    "message": "<MESSAGE>",
    "type": "<TYPE>",
    "code": 0,
    "error_data": {
      "messaging_product": "whatsapp",
      "details": "<DETAILS>"
    },
    "error_subcode": 0,
    "fbtrace_id": "<FBTRACE_ID>"
  }
}
```

`error_data.details` is the human-useful string; `message` is often generic. `fbtrace_id` is the provider request ID — log it, it is what Meta support asks for.

### Code classification

| Codes | Meaning | Taxonomy class | Retryable |
|---|---|---|---|
| `0`, `190`, `200` | auth failed / token expired / no token | `authentication` | no |
| `3`, `10`, `131005` | permission not granted or removed | `permission` | no |
| `4`, `80007`, `130429` | app / WABA / throughput rate limit | `rate_limited` | **defer, do not count an attempt** |
| `131048`, `131056`, `131064` | sender restrictions, per-recipient flood, quality-based limit | `rate_limited` | defer |
| `133016` | registration attempt limit | `rate_limited` | defer |
| `131021` | sender and recipient identical | `recipient_invalid` | no |
| `131026` | not a WhatsApp user / undeliverable | `recipient_invalid` | no |
| `132001` | template missing or unapproved in that language | `template_invalid` | no |
| `132015` | template paused for low quality | `template_invalid` | no |
| `131047` | >24h since the recipient last replied | `policy_restricted` | no — resend as a template |
| `131049`, `131050` | ecosystem engagement block / marketing opt-out | `policy_restricted` | no |
| 5xx, timeout | | `provider_unavailable` / `network_timeout` | yes |

Rate limits deferring rather than failing is not a WhatsApp nicety — it is the exact bug ADR-012 fixed for Telegram, where three 429s marked a perfectly good message permanently failed.

## Rate limits

- **Throughput:** 80 messages per second per business phone number by default, upgradable.
- **Per recipient:** 1 message every 6 seconds to the same user (~10/minute, ~600/hour); bursts of up to 45 messages in 6 seconds are allowed, followed by a proportional wait.
- **API calls:** 200 requests/hour per app per WABA by default; 5000/hour per app per *active* WABA (one with a registered number).

The per-recipient limit maps directly onto the foundry's existing `rate_limit_chat_seconds` throttle attribute, which Telegram sets to 1. WhatsApp sets it to 6.

## Customer service window

Error `131047` — "More than 24 hours have passed since recipient last replied" — establishes the window at **24 hours from the last inbound customer message**. The overview page names the window but does not state its duration, so the code above is the citation.

Outside the window, only approved template messages are deliverable. The adapter must check before sending, and the value belongs in a named constant with this citation beside it, not scattered as a literal.

## Onboarding a number — the steps a human has to do

Nothing below can be done from Odoo, and none of it needs a developer. It is
written out because the module was built without credentials and somebody will
have to do this before a single message is delivered.

1. **Meta Business Manager** — have or create a Business account, and add the
   WhatsApp Business Account (WABA) to it.
2. **Add a phone number.** Use a number that is *not* currently in the WhatsApp
   Business mobile app on someone's phone, and not a number the business cannot
   afford to lose from that app. Coexistence is not assumed to work — ADR-005 —
   so test with a dedicated number before migrating an important one.
3. **App Dashboard → API Setup.** Record two values: the **WhatsApp Business
   Account ID** and the **Phone number ID**. Both go on the Odoo account form's
   WhatsApp page.
4. **Business Settings → Users → System Users.** Create a system user, assign
   the app and the WABA to it as assets, and generate a token with exactly
   these permissions:
   - `business_management`
   - `whatsapp_business_messaging`
   - `whatsapp_business_management`
   The temporary token on the API Setup page is not suitable — Meta's own guide
   says it "expires quickly".
5. **Enter the credentials in Odoo**, on the account's Credentials page:
   - access token → *Bot Token / API Key*
   - app secret (App Dashboard → Settings → Basic) → *API Secret*
   - a verify token you invent → *Webhook Secret*

   Enter them yourself. They must never be pasted into a chat, a commit, a
   handoff entry or a ticket.
6. **Press Test Connection.** It reads the phone number node — no message is
   sent to anybody. Success shows the verified business name.
7. **Configure the callback.** Press *Show Callback URL* on the WhatsApp page,
   then in App Dashboard → WhatsApp → Configuration paste that URL and the same
   verify token, and **subscribe the WABA to the `messages` field**. Without
   that subscription no inbound message and no delivery status ever arrives.
   The instance must be reachable over public HTTPS; Meta will refuse anything
   else.
8. **Get templates approved** for every language you intend to send in, then
   record each one under Configuration → WhatsApp Templates against the
   matching notification template code.

### Rotation

Regenerate the system user's token in Business Settings and replace the value
in the account's *Bot Token / API Key* field. The old token stops working when
it is regenerated, so do the two together and press Test Connection after.

To revoke without replacing: remove the system user's asset assignment, or
delete the system user. Confirm the current exact procedure at the time —
Meta moves this UI.

**Do not** respond to an authentication failure by generating a fresh temporary
dashboard token. It will work for a few hours and fail again, and the outage
will look intermittent rather than caused.

## Endpoints still to verify before use

- template management / approval status sync (only needed if template sync moves beyond manual identifiers);
- media upload and download;
- phone number node readable fields, for a richer test-connection diagnostic.

## Implementation note

The channel adapter must implement the foundry adapter contract in `../notification_foundry/ADAPTER_CONTRACT.md`, extended per `../conversation_foundry/ADAPTER_CONTRACT.md`. Automated tests must use mocked responses and sanitized fixtures, not live API calls.
