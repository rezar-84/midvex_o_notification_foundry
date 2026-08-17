# Changelog — Conversation Foundry

## 19.0.1.0.1 — 2026-08-17

Cosmetic only. The module had no `static/description/icon.png`, so its card in
Settings → Apps fell back to Odoo's generic placeholder.

Added `icon.svg` (the editable master, read by nothing) and the `icon.png`
rendered from it: the notification foundry's rounded square and purple gradient,
with two speech bubbles in place of the bell — one inbound in white, one
outbound in the house accent.

No `web_icon` and no `application` flag. Conversations stays a menu under the
Notifications root by design, so there is no home-screen tile for an icon to sit
on; only the Apps list card was missing artwork. Odoo reads the card icon from
disk when the module list is scanned, so **no module upgrade is needed** — an
*Update Apps List* (or a restart) is enough.

## 19.0.1.0.0 — 2026-08-15

First implementation. Roadmap phase 3: a provider-neutral conversation can be
created and replied to.

**Models**

- `midvex.conversation.identity` — how one person is addressed on one channel.
  Company-scoped, because the same number contacting two companies in a group
  is two relationships. Matched on the normalized identifier alone; never on a
  display name, which the person controls and changes.
- `midvex.conversation.thread` — the conversation. Survives the customer
  changing channel, carries the assignment, the status and the
  first-response time.
- `midvex.conversation.session` — one channel's leg of a thread. Where the
  company invariant is enforceable, because it is the only record touching both
  the thread and the channel account.
- `midvex.conversation.message` — the durable record, with a monotonic delivery
  ladder that only climbs.
- `midvex.conversation.assignment.event` — append-only audit of who handed what
  to whom.

**Service API** (`services/conversation.py`) — `ensure_identity`,
`ensure_thread`, `open_session`, `record_inbound`, `queue_outbound`,
`add_internal_note`, `apply_status`, `assign`, `resolve`, `reopen`. Adapters and
bridges call these; they do not `create()` on the models. That seam is what
keeps the company invariant, the state machine and the audit trail enforceable
in one place instead of re-implemented per channel.

**Two decisions settled** — both had been flagged in this project's own docs as
"decide with an ADR before writing code":

- **ADR-019**: one inbound envelope store, shared. The webhook is already
  shared, so a second table would mean the controller choosing which one an
  event belongs in before it has parsed it, and would split the dedupe key
  space in two.
- **ADR-020**: conversation replies go out through the one delivery queue. The
  notification foundry gained an optional destination so a customer — who is
  not a staff recipient — can be addressed, and its throttle now keys on that
  destination.

**Notable behaviour**

- **A customer replying to a resolved thread reopens it.** Appending silently
  would file their message where nobody is looking.
- **An unclaimed thread stays in the unassigned queue** when a message arrives,
  rather than moving to "waiting on agent" — which would name an agent who does
  not exist.
- **An internal note has no session**, therefore no delivery job, therefore
  nothing that could accidentally reach the customer. It also does not count as
  answering them.
- **A job awaiting retry is not shown as failed.** It has not failed, and
  saying so would have an agent apologise for a message that is about to
  arrive.
- **History and audit are append-only** by access rights. Nobody, including
  administrators, has unlink on messages or assignment events.

**Not included**

- Any channel. This is provider-neutral by design and tested against an
  in-memory fake; wiring WhatsApp to it is `midvex_o_conversation_whatsapp`,
  and is the obvious next step.
- The agent inbox proper. There are working list, form and search views and a
  menu, but no compose box — replying is a service call. Phase 4.
- CRM linkage, lead creation, quotations. Phases 4 onward.
- AI of any kind. Phase 8, and per ADR-007 never a transport dependency.

69 tests.
