# Handoff Log

## 2026-08-01 — Project scaffold and Telegram MVP implementation started

- **Decision:** Build the shared notification foundry and a Telegram vertical slice in this monorepo, mirroring the `midvex_marketplace_foundry` architecture (core foundry + thin channel adapters). Email/Slack/WhatsApp remain deferred, blank-template docs only.
- **Current milestone:** Foundry skeleton, governance documents, and core + Telegram implementation.
- **Remote:** `git@github.com:rezar-84/midvex_o_notification_foundry.git` was supplied. SSH authentication was not available in this agent session (`Permission denied (publickey)` for the machine's key even after the user added it to GitHub) — the repo was `git init`'d locally with `origin` pointed at that URL, but no fetch/push was performed. Retry `git ls-remote` before the next push.
- **Product decision:** Telegram updates are received via webhook, not long polling (explicit user choice) — requires a public HTTPS URL for `setWebhook`, which the local dev instance does not currently have (`proxy_mode = False`, bound to `127.0.0.1`). The module installs and runs without one; live delivery/inbound-linking testing is blocked until a public URL (or tunnel) and a real bot token are available.
- **Next handoff:** Complete the addon implementation, symlink into `custom-addons`, install/upgrade with `--stop-after-init`, run tagged tests, then perform a live smoke test once the two prerequisites above (public URL, bot token) are resolved.

## 2026-08-01 — Foundry and Telegram MVP implemented and validated

- **Implemented:** `addons/midvex_o_notification_foundry/` (channel/account/recipient/template/rule/message/log/inbound-event models, `services/registry.py` + `services/dispatcher.py`, tiered security groups + company-scoped record rules, dashboard views/menus, a 5-minute queue-drain cron) and `addons/midvex_o_notification_telegram/` (stdlib-`urllib` Telegram Bot API adapter, an inbound webhook controller with `X-Telegram-Bot-Api-Secret-Token` verification and `/link <code>` recipient linking, the demo `crm.lead` "on create" `base.automation` + `ir.actions.server` wiring, and a starter `notification.rule`/`notification.template` pairing it to Telegram). Event wiring is non-invasive (generic `base.automation`, no `crm.lead` inheritance), per `docs/projects/notification_foundry/DECISIONS.md` ADR-006/009.
- **Odoo discovery:** Symlinked both addons into `/home/rubuntu/Development/odoo19-dev/custom-addons/`.
- **Bugs found and fixed during validation (all via real installs/tests, not just review):**
  1. `res.groups` has no `users` field in this Odoo 19 build (renamed to `user_ids`/`all_user_ids`); `services/dispatcher.py::enqueue_event` used `.users` and silently resolved an empty audience. Fixed to `audience_group_ids.all_user_ids`.
  2. `midvex.notification.account.message_ids` collided with the reserved `message_ids` field `mail.thread` already defines (the account model inherits `mail.thread` for chatter) — creating a `midvex.notification.message` corrupted the mixin's field metadata and raised `ValueError: Invalid field midvex.notification.message.message_type`. Renamed to `notification_message_ids`.
  3. Two "same label" UI warnings (`midvex.notification.log.message`/`message_id`, `midvex.notification.template.model_id`/`model_name`) — related fields inherit their source field's label by default; fixed with explicit `string=`.
  4. Test-only: `TransactionCase`'s default `env.user` is the inactive system user, and Many2many-to-`res.users` reads apply an implicit `active_test` filter that hides inactive users — `test_notification_dispatch.py` used `cls.env.user` as the rule audience, which silently resolved to zero recipients. Fixed by creating a dedicated active test user (no production code change needed; real users are active).
- **Validated:** Python compilation and XML/CSV parsing passed for both addons. Both modules installed cleanly into `odoo19_dev` (`-i midvex_o_notification_foundry,midvex_o_notification_telegram --stop-after-init`) and upgraded cleanly afterward. Full fresh-database tagged test run (`odoo19_test_notification_fresh5`, `-i ... --test-enable --dev=none`): **0 failed, 0 error(s) of 15 tests** (11 foundry, incl. model constraints, security/self-vs-manager link-code checks, and a mocked end-to-end dispatch test proving rule→queue→fake-adapter-send→log plus idempotency and unlinked-recipient skipping; 4 Telegram adapter tests + webhook secret-token verification tests). Temporary test databases were dropped afterward.
- **Remote still blocked:** `git ls-remote git@github.com:rezar-84/midvex_o_notification_foundry.git` still returns `Permission denied (publickey)` as of this session, despite the user reporting the key was added. No push has been attempted; the repo remains a local-only `git init` with `origin` configured.
- **Known gaps (documented, not blockers to the local build):** No public HTTPS URL is configured for this dev instance, so `setWebhook`/live inbound linking/live delivery have not been tested end-to-end — only mocked. No real Telegram bot token has been supplied.
- **Next handoff:** Resolve GitHub SSH access (or switch to an HTTPS token) and push. Once a bot token and a public URL/tunnel exist: create a real `midvex.notification.account` for Telegram, run `action_test_connection` and `action_register_webhook`, link a real user via `/link <code>`, add that user to the demo "CRM lead created -> Telegram" rule's audience, create a test `crm.lead`, and confirm the Telegram message arrives.

## 2026-08-03 — GitHub SSH access fixed; Telegram `getMe` validated with a real bot token

- **Root cause found for the SSH block:** it was never a missing/rejected key. `ssh -vT git@github.com` showed GitHub accepting the public key over the wire, then failing locally at `read_passphrase: can't open /dev/tty` — `~/.ssh/config` sets `IdentityAgent none` for all hosts, so ssh refused to use the already-unlocked key sitting in the running agent (`ssh-add -l` showed it loaded) and instead tried to re-read the encrypted private key file with no TTY available to prompt for the passphrase. Fix: `git config core.sshCommand "ssh -o IdentityAgent=$SSH_AUTH_SOCK"` in this repo only (global `~/.ssh/config` left untouched). `git ls-remote origin` now exits 0 (repo exists on GitHub, currently empty — no refs). The user's key passphrase was offered but never needed/used.
- **Telegram `getMe` validated with a real bot token** (supplied by the user for this purpose): via `odoo-bin shell` against `odoo19_dev`, created `midvex.notification.account` id=1 (channel `telegram`), set `api_key`, ran `action_test_connection()`. Result: `state=connected`. The shell's default user (`__system__`, uid=1) needed `group_notification_manager` added first — `action_test_connection` enforces `_require_manager()` and the superuser is not implicitly a member of custom app groups. The token was passed via an environment variable into the shell script and was never written to any file or printed; it is not present in this repo.
- **Still blocked:** no public HTTPS URL/tunnel for this dev instance, so `action_register_webhook` / live `/link` linking / end-to-end delivery remain untested outside the mocked adapter tests.
- **Next handoff:** No commits exist yet in this repo despite the working tree being fully implemented — get user sign-off before the first `git add`/`commit`/`push`. Once a tunnel (e.g. ngrok/cloudflared) or public URL is available, call `action_register_webhook` on account id=1, link a real user via `/link <code>`, add them to the demo rule's audience, create a test `crm.lead`, and confirm delivery.

## 2026-08-06 — First commit pushed to GitHub; SSH root cause corrected

- **Repo is now published.** `1fa1c66 "initial base modules"` (70 files, 2,889 insertions — both addons plus all governance/project docs) was pushed to `git@github.com:rezar-84/midvex_o_notification_foundry.git`. `origin/main` matches local `HEAD`; the working tree is clean. This supersedes the previous entry's "no commits exist yet".
- **Correction to the 2026-08-03 SSH diagnosis.** The earlier root cause (`IdentityAgent none` in `~/.ssh/config` forcing a passphrase re-read with no TTY) was **wrong**. A `ssh -vvT` trace showed the handshake reaching `debug1: Server accepts key: /home/rubuntu/.ssh/id_rsa` and then stalling indefinitely — GitHub authenticates the key fine. The hang is local: `~/.ssh/id_rsa` is held by the **gcr / GNOME-keyring agent** (`/run/user/1000/gcr/ssh`), which will not perform the signing operation without a GUI unlock prompt that cannot render in a headless agent session. `ssh-add -l` listing the key is misleading — the agent advertises it but blocks on use. Because it blocks rather than erroring, even `BatchMode=yes` hangs instead of failing fast, which is why prior sessions read it as an auth/permission failure.
- **Workaround used for the push (not persisted):** a throwaway `ssh-agent` was started, the key added to it via an `SSH_ASKPASS` helper, `GIT_SSH_COMMAND` pointed `IdentityAgent` at that socket for the push, and the agent killed immediately afterwards. Nothing was written to `~/.ssh/`.
- **Still-live gotcha:** the repo-local `core.sshCommand` is still `ssh -o IdentityAgent=/run/user/1000/gcr/ssh` (set 2026-08-03), so the **next** push from a session without a working keyring unlock will hang the same way. Either drop that config, or switch `origin` to HTTPS with a PAT.
- **Hygiene:** a working-tree scan for bot-token / `xox*` / `sk-*` / private-key patterns came back clean — consistent with the Telegram token only ever being passed via an environment variable. One transient artifact (`.claude/settings.local.json.tmp.*`, created and deleted by the editor mid-session) was caught by `git add -A` and removed from the index before committing; it is not in the commit.
- **Unchanged blockers:** no public HTTPS URL/tunnel, so `action_register_webhook` / live `/link` linking / end-to-end delivery remain untested outside the mocked adapter tests. The real bot token was never written to disk and is no longer present in this environment — it must be re-supplied for the next live test.
- **Next handoff:** Stand up a tunnel (`cloudflared tunnel --url http://localhost:8069` or ngrok) and close the two remaining Sprint 1 items in one session: `action_register_webhook` on account id=1 → link a real user via `/link <code>` → add them to the demo rule's audience → create a test `crm.lead` → confirm delivery. Sprint 2 (Email) needs no tunnel and can proceed in parallel — but see `IMPLEMENTATION_PLAN.md` Milestone 12 / roadmap Phase 3, which both call for a foundry-hardening pass *before* the second adapter.

## 2026-08-08 — First live link on production; admin panel, channel-code constraint, and bot commands

- **The tunnel blocker dissolved rather than being solved.** Sprint 1 had been stuck since 2026-08-01 waiting on a public HTTPS URL for `setWebhook`. Both modules are now installed on **`erp.varsco.com`**, which *is* a public host, so no tunnel was ever needed there. `getWebhookInfo` confirms a healthy webhook (`url` set, no `last_error_message`, `pending_update_count: 0`), and **a real user completed the `/link <code>` flow** — the first genuine end-to-end inbound event this project has had. Sprint 1's linking item is closed.
- **Live blocker found and diagnosed, fix committed but not yet deployed:** the production account points at a channel whose `code` is `1`, not `telegram`. `get_adapter('1')` raises "No notification adapter is installed for channel 1", and because `enqueue_event` copies `channel.code` onto every message, the failure appears at send time rather than at configuration time. Root cause is a UI gap, not user error: **`midvex.notification.channel` had no view and no menu at all**, so the only way to reach one was the "Create and edit…" dialog on the account's Channel field, which invites a hand-typed code.
- **Three commits this session**, each validated by a real install rather than review alone:
  - `0968306` — the app installed **invisible to everyone**: the three groups were defined and granted to nobody, so the root menu (which requires `group_notification_user`) was hidden even from the admin, and an `application` module appeared to install and then showed nothing. `base.user_admin` now gets `group_notification_admin` on install. Also: search views for all six models (there were none), real forms for Message / Delivery Log / Inbound Events (there were none), list decorations, an `action_retry` for failed and quarantined messages (`action_process` only touches `pending`, so the UI could not retry at all), and warnings on the Rule form for the two silent misconfigurations — no audience means it delivers to nobody, no `trigger_domain` means it matches every record.
  - `9c63d8c` — `channel.code` becomes a **Selection fed by the adapter registry**, so only codes `get_adapter()` resolves can be entered; codes whose adapter module was later uninstalled stay listed so existing records still display. Channels gained a list, form and menu. Plus: `Test Connection` now returns a notification naming the bot (success was previously *silent*, which reads as failure — this is what sent the user hunting), an optional account-level `parse_mode`, an "Open in Odoo" button on alerts built on `/mail/view` so it stays model-agnostic, and an app icon.
  - `41885a0` — the bot understood exactly **one** command and never replied. `/link` was matched with `text.startswith('/link')`, so a successful link and an expired code produced identical output: nothing. Command parsing is now general and validated against a known set, strips the `@botname` suffix Telegram appends in groups, and six commands answer: `/start`, `/help`, `/link`, `/status`, `/mute`, `/unmute`, `/unlink`. Muting is a separate flag rather than archiving, and the dispatcher skips muted recipients **at enqueue time** so unmuting does not deliver a backlog.
- **Bugs caught only because a real install was run** (static checks passed all of them):
  1. Odoo 19 rejects `expand` and `string` on a search view's group-by `<group>`. XML well-formedness and a purpose-written field-resolution pass both waved this through; the install failed with a RelaxNG error.
  2. Making `channel.code` a Selection broke `account.channel_code` and `recipient.channel_code`, which are *related* fields and must match the type of what they mirror — `TypeError` at registry load.
- **Known gotcha, rediscovered:** the 2026-08-01 entry's item 4 (a rule audience set to `env.user` reads back empty in tests, because `__system__` is `active=False` and Odoo filters inactive records out of relational reads) bit again while writing the new tests. It is documented here twice now for a reason — it presents as a dispatcher bug, not a test bug.
- **SSH:** the repo-local `core.sshCommand` pinning this repo to the gcr keyring agent — flagged as a live gotcha in the 2026-08-06 entry — has been **removed**, so the repo now follows the global config like `varsco_com` does (which pushes fine). Pushing still requires a terminal that can prompt for the key passphrase; it cannot be done from a headless agent session.
- **Test status:** 0 failed, 0 errors of 25 tests (26 Telegram cases) on a fresh database, with both modules installed and then upgraded cleanly. Temporary databases were dropped.
- **Not done:** four commits here are **unpushed**. Nothing from this session is deployed to `erp.varsco.com`, so the live instance still has the invisible menu, the unconstrained channel code, the silent Test Connection and the single-command bot.
- **Next handoff:** push, deploy to erp, then close Sprint 1's last item in one pass — repair the account's channel to `telegram`, delete the messages already queued with `channel_code = 1` (they hold a plain copy and will keep failing), set an audience on the shipped rule, create a `crm.lead`, confirm delivery, and delete the test lead. Then features 7–9 as agreed: group-chat recipients, digest/quiet hours, delivery dashboard.

## 2026-08-09 — Group chats, quiet hours, self-wiring rules, a compose wizard, business events

- **Production is currently broken, and this is the first thing to fix.** erp has the new *code* but the old *schema*: recipient views 500 with `column midvex_notification_recipient.kind does not exist`. Odoo only adds columns during a module upgrade, so the model knows about `kind` while the database does not. Nothing here is testable on erp until the upgrade runs. erp is a source install at `/opt/odoo19` (from the traceback), not Docker.
- **Upgrade ordering matters.** Fix the account's channel to `telegram` **before** upgrading. The `19.0.1.1.0` migration repairs each message's `channel_code` from its account, so if the account is still miscoded it faithfully copies the wrong code.
- **Two defects found while starting on more templates, either of which would have shipped silence:**
  1. **Rules created in the UI never fired.** Nothing called `enqueue_event()` on its own — a rule fired only because a `base.automation` ran a server action that called it, and exactly one existed: hand-written, `crm.lead`, on create. Any other model, or `on_write`, matched nothing and reported no error. Rules now maintain that plumbing themselves: **one automation per (model, trigger)**, shared, because `enqueue_event` already walks the whole matching set and a second automation would run it twice. Existing automations are adopted, not duplicated; cleanup is scoped to automations running our own code so an unrelated one is never deleted.
  2. **`on_write` rules would notify once, ever.** The idempotency key carried nothing identifying the *event*, so every write collapsed onto the first key and the rule deduped itself into permanent silence. `write_date` now discriminates the occurrence — for `on_write` only, so `on_create` keys stay byte-identical and nothing already delivered re-sends.
- **A claim I made and then disproved.** Making `message.channel_code` a stored related does **not** repair existing rows: Odoo computes a stored related only where it is marked for recomputation, and an already-populated column is not. A deliberately poisoned row survived a real upgrade untouched. The repair is an explicit post-migration (`19.0.1.1.0`), watched turning `1` back into `telegram`. Do not assume stored-related recomputation on upgrade.
- **A test of mine that passed by luck.** A quiet-hours test derived its window from a fixed date, so it asserted a real hold only when the suite ran late at night — green at 21:40, red at 05:50 the next morning. Time-dependent tests here must be anchored to the real clock (build the window around `fields.Datetime.now()`), because the cron reads the real clock.
- **Shipped:** group-chat recipients (`kind`, with a group forbidden from carrying a `user_id` — the dispatcher resolves user recipients *by* `user_id`, so a group holding one would deliver that person's private alerts to the whole room); quiet hours (held, never dropped; the window crosses midnight, so membership is not `start <= t < end`, and the release instant uses `tz.localize()` because `replace(tzinfo=...)` is an hour out across a DST boundary; both bounds equal reads as *off*, not permanently quiet); the compose wizard replacing the Message Queue's dead Create button; and `midvex_o_notification_business` with six CRM/Sales/Invoicing templates.
- **Why the business content is a third module:** it needs `sale` and `account`, and an adapter should not drag Invoicing onto an install that only wants Telegram. Its rules ship with **no audience** on purpose — guessing one would notify the wrong people, or a whole company. `rule_lead_stage_changed` ships **disabled**: it fires on every write to a lead, not only on a stage change.
- **Chatter:** a "Send on Telegram" entry in the Actions menu, which logs into the record's chatter — not an SMS-style composer tab. Full parity needs ~6 OWL files plus `mail.message`/`mail.notification`/messaging-menu patches (see `odoo/addons/sms/static/src`), an upgrade-fragile surface for a cosmetic gain.
- **Test status:** 0 failed, 0 errors of **78 tests** across all three modules, on `odoo19_notif_grp`. Install of the new module on a fresh database also verified, and the rule-backfill migration watched adopting the hand-written automation rather than duplicating it.
- **Runbook note:** scope test runs with `--test-tags /midvex_o_notification_foundry,/midvex_o_notification_telegram,/midvex_o_notification_business`. Unscoped `--test-enable` on a fresh database runs all of `base` and `crm` first — that run sat for 20+ minutes without reaching our code.
- **Push status corrected:** `origin/main` is at `a497980`, so everything up to and including the channel-code fix **has been pushed** — the "four commits unpushed" in the 2026-08-08 entry, and my repeated claims through this session, were stale after the user pushed from their own terminal. Three commits are outstanding at the time of writing (`25bc7f8`, `e297f3c`, `37c8ba6`). This also explains the production error above: the code reached erp through a deploy, while the module was never upgraded. **Check `git rev-list --count origin/main...HEAD` rather than trusting a previous entry's number.**
- **Not done:** the digest half of feature 8 is not started, and feature 9 (delivery dashboard, which the foundry manifest still advertises in its summary) is untouched.

## 2026-08-09 (later) — Review pass: two mistakes worth not repeating

- **Verifying in a scratch database is not verifying.** Everything above was checked on `odoo19_notif_grp`, a throwaway created that morning, while `odoo19_dev` — the database actually in use — sat at foundry `19.0.1.0.0` the whole time, with none of it installed. The user went looking for the compose wizard and reasonably concluded it did not exist. **Finish by upgrading the database people actually open**, not only the one the tests ran against. `odoo19_dev` is now on `19.0.1.3.0` with all three modules, backed up first to `~/Development/odoo19-dev/backups/odoo19_dev_pre_notif_upgrade.dump`.
- **Put a binding in the module that already owns its dependency.** All four "Send on Telegram" Actions-menu bindings were written into `midvex_o_notification_business`, which needs `sale` and `account` — so an install of foundry + telegram, which is what both `odoo19_dev` and `erp` run, had the composer and **no way to send from a record at all**. `res.partner` needs only `base` and `crm.lead` only `crm`, so two of the four were gated behind Invoicing purely by which file they were typed into. Now: contacts in the foundry, leads in the Telegram adapter, orders and invoices in the business module. Proven by querying `ir_act_server` on a database with the business module *uninstalled* and seeing both bindings present.
- **The upgrade removed the old records cleanly.** Records dropped from a module's data files are deleted on upgrade, so moving the XML ids left exactly one binding per model — worth confirming rather than assuming, since duplicates would show as two identical Actions entries.
- **A real migration test, by accident.** `odoo19_dev` was at `19.0.1.0.0`, so upgrading it ran both migrations against a genuinely old database. The rule backfill adopted the hand-written `crm.lead` automation rather than duplicating it, exactly as designed.
- **Do not import `tests` from a module's `__init__.py`.** The business module did, and every normal server start logged `Importing test framework, avoid importing from business modules and when not running in test mode`. Odoo's loader imports the tests subpackage itself in test mode; all 9 business tests are still collected with the import removed.
- **New regression test:** `test_app_entry_point_is_not_a_dialog` asserts the app's first menu child is not a `target="new"` action. Clicking Notifications opened a Send Message popup instead of the module (`2ade3a1`) and every test passed throughout, because they checked the menu existed rather than what clicking the app did.
- **Test status:** 0 failed, 0 errors of **81 tests**.

## 2026-08-09 (later still) — "Adding a notify-on-contact-change rule broke saving contacts"

Reported as caused by this module. **It is not.** Recorded in full so nobody investigates it a second time, because the suspicion is a natural one and the timing made it look certain.

- **Symptom:** saving a contact raises `MissingError: Record does not exist or has been deleted. (Record: account.account(11270,), User: 2)`, starting right after a `res.partner` / on-update rule was added.
- **Cause:** a contact's `property_account_receivable_id` (or `property_account_payable_id`) points at an `account.account` that has been deleted. The contact form sends that field on save; Odoo's own `account_account._compute_display_name` → `_compute_code` reads `code_store` on the missing record and raises. Nothing in the notification path is involved.
- **How it was proven**, on `odoo19_dev` with the condition reproduced deliberately:

  | write | no automation | with automation |
  | --- | --- | --- |
  | name only | OK | OK |
  | including the account property | MissingError | MissingError |

  Identical with the rule and its automation deleted, so the automation neither causes it nor widens it. `base_automation`'s write hook does snapshot old values (`record[field_name] for field_name in vals`), which is why it looked like a plausible culprit — but the failing read happens regardless.
- **Find the affected contacts** (verified both ways: it returns the row when the condition exists, nothing when it does not):

  ```sql
  SELECT p.id AS partner_id, p.name AS partner, f.field, kv.key AS company_id,
         kv.value::text AS missing_account_id
  FROM res_partner p
  CROSS JOIN LATERAL (VALUES
      ('property_account_receivable_id', p.property_account_receivable_id),
      ('property_account_payable_id',    p.property_account_payable_id)
  ) AS f(field, val)
  CROSS JOIN LATERAL jsonb_each(COALESCE(f.val, '{}'::jsonb)) AS kv
  WHERE jsonb_typeof(kv.value) = 'number'
    AND NOT EXISTS (SELECT 1 FROM account_account a WHERE a.id = (kv.value::text)::int)
  ORDER BY p.id;
  ```

- **Fix:** drop the dangling key so the property falls back to the company default — `UPDATE res_partner SET property_account_receivable_id = property_account_receivable_id - '<company_id>' WHERE id = <partner_id>;`, after a backup. Worth asking how the account was deleted: if a chart of accounts was removed or reimported, journals, tax accounts and invoice lines may hold the same dangling references.
- **Separately noticed:** in `odoo19_dev`, user 2 could not create a `midvex.notification.template` — `AccessError`, no Notifications/Manager group — even though `security/notification_security.xml` grants `group_notification_admin` to `base.user_admin` and the file is not `noupdate`. Not chased down; worth a look, since it means an admin may have to grant themselves the group by hand after install.
- **Housekeeping:** the reproduction pointed contact #1 at the missing account. Its original value was recovered from `backups/odoo19_dev_pre_notif_upgrade.dump` (empty), restored, both throwaway rules and templates removed, and the scratch database dropped. Deleting the throwaway rule also removed its automation on its own, which incidentally exercised `_drop_orphan_automations` against real data.

## 2026-08-10 — Accounting events, a scheduled trigger, and Turkish for all three modules

Asked for: sample Accounting/Invoicing templates, an analysis of which notifications matter most, those notifications built, and a Turkish translation. The user chose the largest option on all three questions (full AR + AP set, add a scheduled trigger, translate all three modules).

### What shipped

- **Eleven new Accounting/Invoicing events** in `midvex_o_notification_business`, taking `account_templates.xml` from one event to twelve. Ranked by what goes wrong when nobody is told:
  - *Cash in*: invoice posted (the receivable exists and the clock starts), partially paid, **customer payment received** on `account.payment` — the only rule that can see deposits, advances and unallocated payments, because money arriving without an invoice is invisible to every `account.move` rule — plus due-in-3-days and overdue.
  - *Risk*: customer credit note posted, posted invoice cancelled, high-value invoice (**ships disabled**; the 100000 in its domain is a placeholder, and a shipped guess either alerts on every invoice or never fires, which look identical from outside).
  - *Cash out*: vendor bill posted, vendor bill paid, vendor credit note.
- **`on_schedule` rules** in the foundry (`19.0.1.4.0`), so a rule can react to a date passing. See ADR-010.
- **Turkish** — `i18n/tr.po` for all three modules, 353 strings, plus the `.pot` each was generated from.
- **Per-recipient language rendering** in the dispatcher. See ADR-011.

### Things worth not rediscovering

- **`base.automation` already does the scheduled scan, correctly.** `_cron_process_time_based_actions` (`base_automation.py:1171`) fires each record **once**, as its date crosses the window between the automation's `last_run` and now, offset by `trg_date_range`, and applies `filter_domain` in the search. A bespoke scanner would have re-implemented all of it.
- **Two independent guards against a 1970 backfill.** `base.automation` defaults `last_run` to the epoch, so a freshly created scheduled automation would treat *every invoice overdue since 1970* as newly due and enqueue the lot on its first run. The primary guard is stamping `last_run = now` at creation; the second is the idempotency occurrence, a constant `-sched`, so a recreated automation cannot re-send anything either.
- **Scheduled automations cannot be shared, and the call must name its rule.** The watched date, the offset and the domain all live on the automation, so "due soon" and "overdue" need one each. And because `enqueue_event` walks every rule matching (model, trigger), without `rule_id` in the server action either automation firing would enqueue **both** rules for any invoice both domains match — every invoice called overdue three days early. `_drop_orphan_automations` needed the matching split: its (model, trigger) headcount cannot see a per-rule automation, so two scheduled rules on one model would keep each other's alive forever.
- **Odoo 19 moved the translation exporter to a subcommand.** `--i18n-export`/`--modules` are gone; it is `odoo-bin i18n export -c <conf> -d <db> MODULE...`, which writes into each module's own `i18n/` folder. `-l pot` **must not** precede the module names — its `nargs='+'` swallows them and the command fails asking for MODULE.
- **Generate the catalogue, never hand-write the msgids.** A msgid that differs from the export by one character is silently untranslated at runtime, and implicit field labels are exported too. 114 of the 353 strings are inherited Odoo strings that already had official Turkish (pulled from `account/i18n/tr.po`, `mail`, `base`, so our wording matches what a Turkish user already sees elsewhere: Fatura, Tedarikçi Faturası, Vade Tarihi, Alıcı, Şablon, Kural).
- **Odoo's own Turkish is wrong in context for some strings.** `State` is an address field in `base` ("İl/Eyalet"), not a status; `Display Name` is "İsim Göster"; `Revoked` is the imperative "Geriye al"; and the activity-status help carries stray backslashes before each colon that would render literally. Those eleven are overridden deliberately, not imported.
- **A probe that looked like a bug and was not.** Calling `_trigger_event` by hand right after `action_post()` returns zero messages. `action_post()` writes to the invoice, which fires the automation, which already enqueued them — the manual call recomputes the same idempotency key and dedupes, exactly as designed. A second write in the *same transaction* also will not re-fire, because `base_automation` guards with `__action_done` in the context. Verify the language path with two separate records, not two writes to one.
- **Recipient searches need `sudo`.** `rule_notification_recipient_self` restricts recipients to `user_id = user.id`, so a shell probe running as OdooBot resolves no targets at all. The real path is always `env['midvex.notification.message'].sudo()._trigger_event(...)` from the server action.
- **Observed, not chased:** the very first invoice of a fresh sequence rendered its alert with an empty `{{ object.name }}` — the automation fires during `action_post` before the number lands. The second invoice rendered `INV/2026/00003` correctly, so this looks like a first-of-sequence artifact rather than a systematic problem. Worth a look if anyone reports a blank invoice number in an alert.

### Verification

- **0 failed, 0 errors of 104 tests** on `odoo19_notif_grp` (`--test-tags=/midvex_o_notification_foundry,/midvex_o_notification_telegram,/midvex_o_notification_business`). Port 8069 was busy from a running dev server, so the runs used `--http-port=8099 --dev=`.
- `msgfmt --check` on all three catalogues: 51 / 280 / 22 translated, no fuzzy and no empty entries. A test in the business module parses each `tr.po` and fails on any empty `msgstr`, because a half-finished catalogue is invisible at runtime.
- **`odoo19_dev` upgraded** (backed up first to `backups/odoo19_dev_pre_scheduled_i18n.dump`) with `--load-language=tr_TR`. All three catalogues logged as loaded; Turkish subjects and bodies confirmed in `midvex_notification_template.subject->>'tr_TR'`.
- **Both scheduled rules verified in the live database**: two distinct automations, `trigger = on_time`, ranges 3/before and 1/after, `invoice_date_due`, the full domain copied to `filter_domain`, and `last_run` stamped at upgrade time rather than 1970.
- **The real cron, end to end** (rolled back): a back-dated invoice produced **one** message on the first `_cron_process_time_based_actions()` run and **still one** after a second run with `last_run` pushed back again — and the due-soon rule did **not** fire off the overdue rule's automation.
- **Turkish end to end** (rolled back): two invoices posted by the same user with `lang` switched between them produced `Invoice posted: …` / `… was posted for …` and `Fatura onaylandı: INV/2026/00003` / `Dil Testi Ltd için INV/2026/00003 onaylandı. | Tutar: 250.0 TRY | Vade: … | Satış Temsilcisi: …`.

### No migration, deliberately

The new fields and the new selection value are pure schema additions, and `_trigger_event` takes `rule_id` as a keyword with a default — so the server actions written before scheduled rules existed keep working untouched. Nothing needed rewriting in place.

### Open

- Nothing is committed. `git status` shows ten modified files and five new paths (three `i18n/` folders and two test files).
- The shipped rules still carry **no audience**, on purpose. They match records and deliver to nobody until one is set — including the two scheduled ones.
- The on-update rules re-fire if a record that still matches is written again. Posted and paid documents are largely locked, so this is quiet in practice; the exception is `rule_payment_received`, where `in_process -> paid` is a second write that still matches. Noted in the data file itself.

## 2026-08-10 (later) — "Is there a Telegram rate limit, and how do we get instant delivery?"

Both halves of the question turned out to be real defects rather than tuning.

### Delivery was never instant

`enqueue_event` only created `pending` rows; nothing sent. The queue cron's five-minute tick **was** the entire delivery latency, so an invoice posted at 10:00:01 alerted at 10:05, and the batch limit of 50 capped the drain rate at ~600/hour — a burst of 200 alerts took twenty minutes.

Fixed with `ir.cron._trigger()` at the end of `enqueue_event`. **Measured on a running server: 0.3s to pick up, cron `lastcall` 2 seconds after the trigger.** A synchronous send would be marginally faster and was rejected — the user's save would then wait on a third party, and a Telegram outage would make posting an invoice slow or fail.

### Telegram's limits, and the one nobody had written down

Confirmed 2026-08-10 at `https://core.telegram.org/bots/faq`: ~1 message/second to a chat, ~30/second overall, and **20 per minute in a group**. The group figure was missing from `API_RESEARCH.md` and is the one a notification rule breaches first — a rule pointed at a shared sales room can exceed it from a single batch. Nothing paced sends at all before this.

### The 429 defect

`_request` parsed `retry_after` and threw it away into an error string. `action_process` caught it as a generic exception, scheduled a flat five-minute retry and **incremented `attempt_count`** — so three 429s, which say nothing whatsoever about the message, marked a perfectly good alert permanently `failed`. Meanwhile `parse_error`, `retryable` and `retry_after_seconds` had been in `ADAPTER_CONTRACT.md` from the start and **nothing had ever called `parse_error`**; Telegram's returned `retryable: False` hardcoded.

### Things worth not rediscovering

- **The queue drained newest-first.** `_order = 'id desc'` is right for the list view and wrong for a queue. Invisible while everything in a batch went out regardless; under a rate limit the newest message wins every run and the oldest alert is deferred repeatedly. `cron_process_pending` now passes `order='id'`. Found by a test, not by reading.
- **Throttle per message, never per batch.** Sending is what consumes the allowance. Checked once for the batch, twenty-five messages to one group all see an empty window and go out together.
- **Defer, don't sleep.** `max_cron_threads = 1` locally, so sleeping to pace a batch holds the only worker and lets one busy room starve every other recipient.
- **Running a cron in `odoo-bin shell` commits, so a "rolled back" probe is not.** `_cron_process_time_based_actions` calls `ir.cron._commit_progress()` mid-run. The earlier overdue probe printed "rolled back" and still left a posted invoice, a partner, an audience on a shipped rule and **a queued Telegram message** in `odoo19_dev`. See the cleanup note below. Probe anything that runs a cron on a scratch database, not on the one people open.
- **Adapter objects are not rolled back between tests.** `send_calls` on a class-level mock accumulates across test methods; reset it in `setUp` or assertions on call counts silently inherit the previous test's sends.
- **Production prerequisite:** none of this runs without a cron worker. Local `config/odoo.conf` has `workers = 0`, `max_cron_threads = 1`. On a deployment with `max_cron_threads = 0` nothing has ever sent, triggered or not.

### Verification

- **0 failed, 0 errors of 120 tests** (up from 104) on `odoo19_notif_grp`, port 8099 because a dev server holds 8069.
- Latency measured against a real running server with a cron worker, on a scratch database whose Telegram account has **no token** — so the send failed locally with no network call, which is enough to prove the cron ran. Result above.
- The probe message came back `attempt_count = 1`, `state = pending`, `error_code = TELEGRAM_ERROR` — the new classification and backoff working on a real run rather than only under a mock.
- `odoo19_dev` upgraded to foundry `19.0.1.5.0`.

### Cleanup of my own mess in `odoo19_dev`

Removed: the queued "INV/2026/00001 for Overdue Probe Ltd is overdue" message, which would have sent a false alert to a real Telegram chat the moment a cron ran, and the audience the probe added to `rule_invoice_overdue` (that rule ships with none, deliberately).

**Still there and left alone deliberately** — deleting posted accounting entries is not something to do unasked: posted customer invoice **INV/2026/00001** (id 25, 575.00) and partner **Overdue Probe Ltd** (id 348), both created by the probe. It also consumed the first number in the 2026 invoice sequence.

### No migration

`hold_reason` is a new nullable column and the batch size has a default, so nothing needed rewriting in place.
