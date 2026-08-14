# Project — Website Live Chat Connector

## Module

```text
midvex_o_conversation_webchat
```

## Depends on

```text
midvex_o_conversation_foundry
```

## Status

**Planned. Not started.** Roadmap phase 5.

## Purpose

Web chat session behavior: visitor and session tokens, online presence, typing and read-state semantics where supported, and conversion of an anonymous visitor into a persistent contact or lead identity.

The browser never talks to this module directly. It talks to `varsco_messaging_api` (see `../messaging_api/`), which talks to the conversation foundry, which uses this module for the webchat channel's specifics.

## The frontend is not Next.js

The source pack states throughout that the public website is a Next.js application. It is not, and no Next.js VARS site exists on this machine. The real frontend is:

```text
~/Projects/Websites/varsco_com
```

TanStack Start + Vite + React, Radix/shadcn, built with Bun, tested with Vitest and Playwright, deployed via Docker and Cloudflare Wrangler. It is **Lovable-connected** — its own `AGENTS.md` carries a `LOVABLE:BEGIN` block warning that commits sync back to the Lovable editor and history must not be rewritten. That constrains how any agent may work in that repository.

See ADR-016. Every "Next.js" in the merged docs has been changed to "the frontend".

## What already exists there

`src/components/layout/WhatsAppWidget.tsx` (119 lines) — a fixed bottom-right popover with four canned quick-topic buttons, internationalized across all nine locales. It builds `https://wa.me/<phone>?text=...` deep links via `src/lib/utils/whatsapp.ts`.

It is **deep-link only**: it hands the visitor to WhatsApp and Odoo never sees the thread. The same is true of the inquiry links in `SiteHeader.tsx`, `SiteShell.tsx`, `CartDrawer.tsx` and the product detail route.

That widget is the shell to absorb, not a competitor to replace. Its UI, its nine-language `whatsapp.topic.*` strings and its placement are all reusable; what changes is where the messages go.

## Documents

| File | Source |
|---|---|
| `PRD.md` | pack `09` |
| `ARCHITECTURE.md` | pack `09` + `04` |
| `API_SPEC.md` | pack `09` + `10` |
| `TEST_PLAN.md` | pack `13`, live chat cases |
