# Operations Runbook — Omnichannel Messaging

## Provenance

Merged from `varsco_omnichannel_messaging_project/18_RUNBOOK.md`. For local development commands see `docs/DEVELOPMENT_RUNBOOK.md` and `~/Development/odoo19-dev/AGENTS.md` — this file is about running the system in production, not building it.

## Daily health checks

Monitor:
- failed outbound queue;
- failed inbound events;
- provider authentication failures;
- invalid webhook spikes;
- unprocessed events;
- conversation backlog;
- realtime connection failures.

## WhatsApp authentication failure

Symptoms:
- outbound 401/403-like provider failure;
- account test fails.

Actions:
1. do not regenerate random temporary tokens as routine workaround;
2. confirm production credential type and asset assignment;
3. verify account enabled;
4. verify provider/API version;
5. rotate credential according to documented process;
6. run test connection;
7. replay only safe failed messages.

The credential onboarding and rotation procedure lives in `../conversation_whatsapp/API_RESEARCH.md`.

## Webhook not receiving

Check:
- public endpoint;
- reverse proxy;
- TLS;
- provider subscription;
- verification secret/signature;
- application logs by correlation ID;
- account mapping;
- rate-limit/firewall.

## Duplicate messages/leads

Check:
- external event/message identifiers;
- inbound dedupe constraint;
- queue retries;
- CRM lead creation transaction boundary.

Never "fix" by disabling provider retries.

## Wrong company concern

Immediately:
1. disable affected channel account if needed;
2. inspect thread/session/account company IDs;
3. inspect record-rule logs/audit;
4. add regression test before restoring.

## Queue backlog

Identify:
- provider outage;
- rate limit;
- worker failure;
- database lock;
- poison event.

Use bounded replay.

A backlog with *no* failures and *no* provider errors usually means no cron worker is running. That is the first thing to check, not the last: with `max_cron_threads = 0` the queue is inert and looks identical to a healthy idle system from the outside.

## AI bad response

1. switch thread/company AI mode to human takeover/off;
2. preserve audit;
3. classify failure;
4. update guardrail/knowledge;
5. regression-test prompt/tool behavior before re-enabling auto.

## Rollback

Module releases should support:
- previous code deployment;
- database schema compatibility planning;
- disabling channel account without deleting conversation history;
- disabling AI independently;
- disabling the website widget independently.
