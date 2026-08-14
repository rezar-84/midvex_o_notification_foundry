# Security and Multi-Company — Omnichannel Messaging

## Provenance

Merged from `varsco_omnichannel_messaging_project/11_SECURITY_MULTI_COMPANY.md`. Read alongside `docs/standards/NOTIFICATION_SECURITY.md`, which governs the notification half and is not superseded by this file.

## Threat model

Protect against:
- leaked provider credentials;
- forged webhooks;
- cross-company message sending;
- customer conversation enumeration;
- duplicate/replay webhooks;
- unauthorized agent access;
- prompt injection through AI/customer messages;
- malicious attachments later;
- excessive message spam;
- sensitive payload leakage in logs.

## Multi-company invariants

Every conversation thread has a company.

Every channel account has a company.

Outbound invariant:

```text
thread.company_id == session.company_id == account.company_id
```

Violation must fail server-side.

Never rely only on domain filters in views.

## Record rules

At minimum:
- Messaging User: conversations in authorized companies and assigned/allowed scope.
- Agent: reply to allowed conversations.
- Supervisor: team/company visibility and reassignment.
- Administrator: configuration within authorized companies.

The existing foundry already ships three groups (`group_notification_user` ⊂ `manager` ⊂ `admin`) and nine record rules in `addons/midvex_o_notification_foundry/security/`. Conversation roles should extend that ladder rather than introduce a parallel one.

## Credential handling

- no secrets in Git;
- no secrets in frontend;
- no secrets in chatter;
- mask secret fields;
- restrict read access;
- use environment/config secret store patterns compatible with the existing project;
- rotation procedure documented.

The foundry's `midvex.notification.account` already gates `api_key`, `api_secret` and `webhook_secret` behind `group_notification_admin`. WhatsApp credentials use those same fields plus the WhatsApp-specific identifiers; they do not introduce a new secret store.

## Webhook security

Provider endpoint must:
1. identify account safely;
2. validate provider verification/signature;
3. reject invalid payloads;
4. rate-limit obvious abuse;
5. dedupe;
6. acknowledge promptly.

For WhatsApp specifically the signature is `X-Hub-Signature-256`, an HMAC-SHA256 over the **raw** request body keyed with the app secret, compared in constant time. See `../conversation_whatsapp/API_RESEARCH.md`.

## Customer web chat

- opaque session identifiers;
- expiring access token;
- per-session authorization;
- rate limiting;
- message size validation;
- escape/sanitize rich content;
- no arbitrary HTML rendering.

## Logging policy

Default operational logs should contain:
- provider;
- company;
- account ID;
- event/message identifiers;
- status;
- error code;
- correlation ID.

Avoid full customer body unless diagnostic mode is explicitly enabled and privacy-approved.

Never log credentials, Authorization headers, or webhook signing secrets.

`midvex.notification.log` already redacts metadata keys named `raw`, `body` and `text`. Conversation logging must not weaken that.

## AI security

AI receives only necessary data.
Never let customer content directly determine:
- Odoo model/domain queries;
- system commands;
- recipients;
- pricing;
- payments;
- company selection.

Tool calls must use allowlisted operations and server-side authorization.

## Attachments later

Before enabling:
- MIME validation;
- size limit;
- malware scanning;
- safe filename handling;
- Odoo attachment ACL review;
- download authorization.
