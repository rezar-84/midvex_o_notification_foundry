# API Research — WhatsApp Conversation Connector

The WhatsApp Cloud API research is maintained in one place and shared by both WhatsApp projects:

**→ `../notification_whatsapp/API_RESEARCH.md`**

It covers the pinned Graph API version, credentials and scopes, the send endpoint and payloads, webhook verification and `X-Hub-Signature-256` validation, inbound message and status payload shapes, status mapping, the error envelope with a code-to-taxonomy table, rate limits, and the customer service window.

Duplicating it here would guarantee the two copies drift, and a stale API version in a file named `API_RESEARCH.md` is worse than no file. Anything genuinely specific to two-way conversation — media handling, interactive message types, template sync — gets added there under a conversation heading and cross-linked from `ARCHITECTURE.md`.

Last verified: **2026-08-14**, Graph API v26.0 latest, v25.0 pinned.
