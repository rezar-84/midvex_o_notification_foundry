# Test Plan — WhatsApp Conversation Connector

## Provenance

The WhatsApp cases from `varsco_omnichannel_messaging_project/13_TEST_PLAN.md`. General layers and philosophy are in `../conversation_foundry/TEST_PLAN.md`.

## Rule

No automated test may call the Meta API. Every payload in this plan comes from a sanitized fixture with tokens, phone numbers and message bodies replaced.

## Mandatory cases

| Case | Layer | Phase |
|---|---|---|
| Webhook verification challenge (`hub.mode`/`hub.verify_token`/`hub.challenge`) | controller | 2 |
| Valid `X-Hub-Signature-256` accepted | controller | 2 |
| Forged signature rejected with 403 | controller | 2 |
| Missing signature header rejected | controller | 2 |
| Body mutated after signing rejected | controller | 2 |
| Duplicate webhook delivery creates one record | controller | 2 |
| Destination company resolved from the account | controller | 2 |
| Unsupported message type stored without crashing | controller | 2 |
| Out-of-order delivery statuses (`read` before `delivered`) | integration | 2 |
| Provider 4xx classified permanent, stops retrying | integration | 1 |
| Provider 5xx classified retryable | integration | 1 |
| Timeout classified retryable | integration | 1 |
| Rate limit defers without consuming an attempt | integration | 1 |
| Invalid token surfaces a safe diagnostic | integration | 1 |
| Expired/revoked token surfaces a safe diagnostic | integration | 1 |
| Template rejection classified permanent | integration | 1 |
| Wrong-company account send blocked server-side | transaction | 1 |
| E.164 variations of one number match one identity | unit | 3 |
| Unknown phone creates a provisional identity | unit | 3 |
| Known partner links without duplicating | unit | 3 |
| Multiple possible partner matches handled deterministically | unit | 3 |
| Resolved conversation receiving a new message reopens | transaction | 3 |

## Fixtures needed

- inbound text message
- inbound unsupported type (sticker or reaction)
- status: sent / delivered / read / failed
- error envelope: auth, rate limit, template invalid, recipient invalid
- verification challenge query string

Store them as Python dicts beside the tests, as `test_telegram_adapter.py` does, not as JSON files — the existing suite has no fixture-loading helper and adding one for five payloads is not worth it.

## Secret hygiene in tests

The repo's own scan, already allowlisted in `.claude/settings.local.json`, must pass over every fixture before commit. A real WABA token in a test fixture is a committed credential regardless of the file's name.
