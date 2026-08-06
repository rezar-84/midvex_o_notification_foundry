# PRD — Slack Connector

## Goal

Connect the notification foundry to Slack.

## Functional requirements

- Configure Slack bot/webhook credentials per notification account.
- Test connection.
- Send a rendered message to a linked recipient's Slack user/channel.
- Handle rate limits and retryable errors.
- Log all API operations.

## Provider-specific fields to verify

```text
bot token, signing secret, workspace identifiers
```

Do not implement these blindly. Verify from the latest official docs.

## Non-goals for MVP

- interactive components/buttons;
- slash commands;
- multi-workspace app distribution.
