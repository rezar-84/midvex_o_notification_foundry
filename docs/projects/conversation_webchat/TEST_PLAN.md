# Test Plan — Website Live Chat

## Provenance

The live chat cases from `varsco_omnichannel_messaging_project/13_TEST_PLAN.md`. General layers are in `../conversation_foundry/TEST_PLAN.md`.

## Cases

| Case | Layer | Asserts |
|---|---|---|
| Create session | HTTP | opaque `public_id` returned, no Odoo ID leaked |
| Expired token | HTTP | rejected, same error as a nonexistent session |
| Guessed ID | HTTP | rejected, indistinguishable from expired |
| Spam rate limit | HTTP | bounded per session and per source, at create and at send |
| Customer reload/reconnect | HTTP | history restored, no duplicate thread |
| Multiple browser tabs | HTTP | one session, consistent ordering across tabs |
| Agent response | transaction | reaches the browser transport |
| Offline state | HTTP | availability reported without promising a response time |
| Handoff to WhatsApp | transaction | new session, **same** thread, CRM linkage preserved |

## Security cases that matter more here than elsewhere

The webchat surface is the only one an anonymous stranger can reach directly. Beyond the table above:

- **HTML/script content in a message body** must survive storage and never render as markup.
- **Oversized payload** must be rejected at the controller, before parsing, not after.
- **Company crossover** — a session created against one company must never read or write another's thread, asserted at the model layer and not only by a route domain.

## No live dependency

Nothing in this plan may depend on a running frontend, a real browser, or a network. Realtime transport tests assert what the server pushes, not what a browser receives; the browser half belongs in `varsco_com`'s own Playwright suite.
