# Changelog — Notification Foundry

## Unreleased

- Initial project documentation.
- Notification suite architecture defined.
- Data model defined.
- Adapter contract defined.
- Implementation and test plans created.
- Added monorepo governance, sprint backlog, development runbook, handoff log, and MVP decisions.
- Added initial foundry and Telegram MVP addon implementation.
- Added `on_schedule` notification rules, driven by `base.automation`'s `on_time` (foundry 19.0.1.4.0).
- Messages render in the recipient's language instead of the acting user's.
- Added eleven Accounting/Invoicing templates and rules, including overdue and due-soon (business 19.0.1.2.0).
- Added Turkish translations for all three modules.
- Notifications are delivered within seconds via an `ir.cron` trigger instead of waiting for the five-minute queue tick (foundry 19.0.1.5.0).
- Sends are paced inside the channel's declared rate limits; breaching messages are deferred, not dropped.
- Rate-limited sends no longer count as delivery failures; permanent errors quarantine, and retries back off.
