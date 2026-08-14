# Test Plan — Headless Messaging API

## Provenance

The HTTP/controller and security layers of `varsco_omnichannel_messaging_project/13_TEST_PLAN.md`. General layers are in `../conversation_foundry/TEST_PLAN.md`.

## Layer

Odoo `HttpCase`, not `TransactionCase` — these are routes, and the auth, CSRF and error-envelope behavior only exists at the HTTP layer.

## Customer surface

| Case | Asserts |
|---|---|
| Create session returns an opaque ID | no database ID in the response, anywhere |
| Valid token reads its own history | |
| Expired token rejected | |
| Another session's token rejected | **identical** response to expired — no enumeration oracle |
| Nonexistent public ID rejected | identical again |
| Rate limit at session creation | bounded per source |
| Rate limit at message send | bounded per session |
| Oversized body rejected | before JSON parsing, not after |
| Script content in a body | stored intact, never rendered as markup |
| Company resolved server-side | a company parameter in the request is ignored, not honored |

## Agent surface

| Case | Asserts |
|---|---|
| Unauthenticated request rejected | |
| Authenticated user sees only their companies' conversations | record rules, asserted at the model layer too |
| Cross-company read denied | |
| Cross-company assign denied | |
| Resolve / reopen transitions audited | |
| Pagination bounded | no unbounded list route |

## Envelope

Every response, success and error, carries `meta.correlation_id`. Every error carries a stable machine-readable `code`. No response contains a stack trace, an ORM message, a model name, or a field name.

Assert this on the error paths specifically — success responses tend to get the attention, and it is the 500 handler that leaks.

## No live dependency

No test may require a running frontend, a browser, or a network.
