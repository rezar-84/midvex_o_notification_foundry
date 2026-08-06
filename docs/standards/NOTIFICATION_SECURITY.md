# Notification Security

## Credentials

- Store bot tokens, webhook secrets, and API keys securely.
- Mask credentials in forms and logs.
- Restrict credential editing to notification administrators.
- Never commit credentials.
- Never put credentials in test fixtures.
- Never print credentials.

## Webhooks

- Verify signatures/secret tokens where available (e.g. Telegram's `X-Telegram-Bot-Api-Secret-Token` header).
- Restrict endpoints to the expected channel and account.
- Store raw inbound payload in protected records (`midvex.notification.inbound.event`, admin-only).
- Process webhook payloads asynchronously where the workflow allows it (queue, don't inline heavy logic in the controller).
- Handle replay protection where possible (dedupe on provider update id where the channel supplies one).

## Access groups

Recommended groups:

```text
Notification User
Notification Manager
Notification Administrator
```

## Data privacy

Notification recipients and message bodies may include personal data (names, chat identifiers, message content). Protect recipient identifiers and message bodies.

Do not expose message body content in technical logs beyond what is required for troubleshooting.

## Production safety

- Do not use production channel credentials in automated tests.
- Do not send test messages to real recipients from a test database.
- Use a dedicated test/sandbox bot or account where available.
- If no sandbox exists, add a dry-run mode and manual confirmation before enabling a live channel account.
