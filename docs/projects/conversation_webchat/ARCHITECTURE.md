# Architecture — Website Live Chat

## Provenance

The webchat slice of `varsco_omnichannel_messaging_project/04_ARCHITECTURE.md` and `09_LIVE_CHAT_SPEC.md`.

## Layering

```text
Browser (varsco_com, TanStack Start)
   |  opaque session token, no Odoo IDs, no provider secrets
   v
varsco_messaging_api          <- HTTP surface, auth, rate limits
   |
   v
midvex_o_conversation_webchat <- session semantics, presence, identity conversion
   |
   v
midvex_o_conversation_foundry <- thread, message, identity, assignment
   |
   v
Odoo (contacts, CRM, sales)
```

Three rules hold this shape:

- The browser never reaches Odoo models. It reaches one versioned HTTP surface.
- No provider credential exists anywhere above the adapter layer — and webchat has no provider at all, which is precisely why it is the cheapest channel to get right first.
- Company resolution happens server-side, from the session's origin, never from a request parameter.

## Why webchat is a channel and not a special case

It is tempting to treat "our own website" as privileged and skip the adapter. Don't. Modelling webchat as one more `channel_code` behind the same registry is what makes the web-to-WhatsApp handoff a *session* change inside one thread rather than a data migration between two systems.

The webchat adapter's `send()` does not call an external API; it pushes to the realtime transport. Everything else about it — capabilities, identity normalization, the DTO shapes — is the same contract every other channel implements.

## Session tokens

An opaque, expiring, revocable token scoped to exactly one chat session. Requirements:

- generated server-side from a cryptographic source, never derived from a database ID;
- stored hashed, compared in constant time;
- carries no company, partner, thread or lead identifier that a client could enumerate;
- expiry short enough to matter, with refresh on activity so a live conversation does not die mid-sentence;
- revocable individually, so one abusive session can be cut without touching anyone else.

## Presence and realtime

Preferred transport is SSE or WebSocket. The Odoo bus may sit behind the gateway if it proves reliable through the deployment's reverse proxy — that is a question to answer by testing against the real proxy, not by reading Odoo's documentation.

Bounded long-polling is the fallback. Constant 1–2 second polling is not an acceptable implementation at any point, including "temporarily".

## Identity conversion

A visitor starts anonymous and becomes a `res.partner` at a moment the business chooses, not automatically on first keystroke. The pre-chat form collects the minimum (name, plus email or phone); the conversion policy — provisional contact, lead, or neither until qualified — belongs in `midvex_o_conversation_crm`, not here.

What this module owns is making the conversion *possible* without losing message history: the thread exists from the first message, and acquiring an identity attaches to it rather than starting a new one.

## Relationship to `varsco_content_api`

That addon already exposes `/api/v1/*` to this frontend, including multi-company lead routing on `POST /api/v1/leads`. It is the precedent for route shape, error envelope and company resolution — read it before designing anything here.

It is **not** the place to put messaging. Per the source pack: keep the existing public content API stable and create `varsco_messaging_api` beside it. See `../messaging_api/`.
