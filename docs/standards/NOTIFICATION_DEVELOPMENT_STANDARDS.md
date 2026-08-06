# Notification Development Standards

## Odoo standards

- Use Odoo 19 APIs.
- Do not edit core.
- Use model/view inheritance, not monkey-patching of unrelated modules' models (e.g. `crm.lead`).
- Keep channel modules thin.
- Make UI strings translatable.
- Support multi-company.
- Add tests for every workflow.
- Use batch operations.
- Avoid long HTTP request operations.
- Use jobs (queue + cron) for external delivery, never inline in the triggering transaction.
- Avoid raw SQL unless justified.

## API standards

- Use timeouts.
- Handle rate limits.
- Normalize errors.
- Log request references.
- Do not log secrets (bot tokens, webhook secrets, API keys).
- Use retries only for retryable errors.
- Mock external APIs in tests.
- Version channel API assumptions.

## Channel standards

- Respect each channel's rate limits and message-size limits.
- Never hard-code a channel's numeric/account identifiers into code; store them in models.
- Support per-company channel accounts.
- Provide a test-connection action before enabling a channel account.
- Handle channel-reported delivery failures distinctly from transport failures.

## Template standards

- Templates render through Odoo's own rendering (`mail.render.mixin`), not a custom engine.
- Never allow template bodies to execute arbitrary code — only variable substitution against the triggering record.
- Templates must declare which model they render against.
- Provide sensible fallback text if a variable is missing.

## Delivery/retry standards

- Every outbound message gets an idempotency key derived from (rule, record, recipient, channel).
- Retries use exponential backoff with a max-attempts cap.
- Non-retryable errors (e.g. invalid recipient) must not be retried.
- Duplicate triggers for the same event must not create duplicate queued messages.

## Log standards

- Log delivery attempts, status, and channel error codes.
- Redact message-body content from default log verbosity where practical; keep it only on the message record itself, access-restricted.
- Preserve the channel's raw error reference for troubleshooting without logging secrets.
