# Test Plan — WhatsApp Connector

## Automated (`addons/midvex_o_notification_whatsapp/tests/`)

76 tests, no live API call anywhere. Payloads come from `tests/fixtures.py`,
whose shapes are Meta's published examples with every identifier, phone number,
name and body replaced.

### `test_whatsapp_adapter.py`

- **Client** — the pinned API version, the per-account override, a missing token
  refused before any request, and the provider's numeric code and `fbtrace_id`
  surviving into the exception. An unreadable error body still produces an
  error rather than a parse failure.
- **Send** — text and template payload shapes; a missing recipient refused; and
  a 200 carrying no `wamid` treated as a failure, because marking it sent would
  leave a row no status webhook will ever mention again.
- **Test connection** — reads the phone number node, which proves token, asset
  assignment and phone number ID in one call that messages nobody.
- **Error classification** — every taxonomy class against Meta's own codes:
  rate limits defer with a delay, authentication and permission are permanent,
  `131047` (closed messaging window) is permanent, unknown codes retry, and a
  plain non-WhatsApp exception does not crash classification.
- **Inbound parsing** — text, unsupported types recorded rather than dropped,
  statuses, several messages in one notification, and empty or unknown payloads
  returning nothing instead of raising.
- **Identity** — five spellings of one number normalizing alike.
- **Registration** — the adapter resolves under `whatsapp`, the channel record
  ships, and the rate limits are declared where `_throttle_release_at` reads them.

### `test_whatsapp_templates.py`

Mapping lookup (exact language, base-language fallback, never a *different*
language), archived and cross-account isolation, positional variable
substitution, a missing variable becoming empty rather than raising, and the
unique constraint. Then the whole path from a queued message to the payload on
the wire, including that the mapping is looked up in the recipient's language
and not the acting user's.

### `test_whatsapp_webhook.py`

Signature verification against forgery, another secret, a body altered after
signing, a missing header, a header without the algorithm prefix, and
re-serialized JSON — that last one being the mistake this code is shaped to
avoid. Failing closed with no secret configured. The dedupe key, its unique
constraint, and that Telegram's NULL keys coexist freely. The delivery ladder,
including `read` before `delivered`.

## Foundry integration

Not duplicated per channel. `midvex_o_notification_foundry/tests/test_notification_dispatch.py`
already proves the rule/queue/registry pipeline against any registered adapter,
and `test_rate_limits.py` proves that an adapter's declared limits are honoured
and that a rate limit does not consume an attempt.

## Not covered by automated tests

Everything that needs a real WhatsApp Business account:

- a real credential test connection;
- live delivery of an approved template message;
- a genuine signed webhook from Meta;
- real delivery and read statuses arriving over the wire;
- whether the system-user token behaves as the documentation implies over time.

That list is the outstanding work, not an accepted gap. See the handoff log.

## Known environmental failure

On a **fresh** test database with no chart of accounts, three tests in
`midvex_o_notification_business` error while creating an `account.move` or
`account.payment` with no journal. Verified 2026-08-14 to be independent of this
module: a control run of the three original modules, with WhatsApp not
installed, produces the identical three errors.
