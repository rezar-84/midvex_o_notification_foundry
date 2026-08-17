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

## 2026-08-10 (end of session) — The app icon, and where everything was left

### The icon

Reported as "Odoo still shows the old icon of the app". It was not a cache problem and not an old file: the icon had **never** been shown on the home screen.

Odoo has two app icons and they are easy to conflate:

| Where | Driven by | Was |
|---|---|---|
| Apps list card (Settings → Apps) | `static/description/icon.png` | ✅ present since August |
| Home screen tile | `web_icon` on the root `ir.ui.menu` | ❌ never set |

`menu_notification_root` declared no `web_icon`, so the tile fell back to a generic placeholder, and **replacing the PNG could never have changed it**. Confirmed in `odoo19_dev` before the fix: `web_icon` empty, zero `web_icon_data` attachments. After: one `image/png` attachment of 7827 bytes, which is `icon.png` byte for byte.

Worth keeping in mind: `web_icon_data` is an attachment written only when `web_icon` is written (`ir_ui_menu.py:155-156, 161-162`) and is **never re-read from disk**. Swapping the PNG therefore shows nothing until an upgrade rewrites the attribute. That is now recorded in a comment beside the menuitem.

`icon.svg` sits next to the PNG as the editable master and is read by nothing — Odoo wants the PNG. Do not edit only the SVG and expect a change.

### Where things stand

- **`main` is 11 commits ahead of `origin/main` and nothing is pushed.** Three merge commits this session: `822e07a` (accounting events, scheduled rules, Turkish), `6844f11` (prompt delivery and rate limits), `78892c4` (the icon).
- Branches `feat/accounting-notifications-scheduled-rules-tr`, `feat/instant-delivery-rate-limits` and `fix/app-home-screen-icon` are merged and can be deleted.
- **0 failed, 0 errors of 120 tests**, re-run on merged `main`, not only on the branches.
- `odoo19_dev` is on foundry `19.0.1.5.1` with all three modules and Turkish loaded. Backed up before the day's upgrades to `backups/odoo19_dev_pre_scheduled_i18n.dump`.

### Open, in the order I would take them

1. **Push.** Everything above is local only. The 2026-08-09 entry's lesson applies: check `git rev-list --count origin/main...HEAD` rather than trusting a number written down.
2. **Set an audience on the shipped rules.** Every rule in the business module ships with none, deliberately — they match records and deliver to nobody until somebody chooses. The two scheduled ones included. Until this is done, none of the new accounting alerts do anything.
3. **Confirm a real end-to-end Telegram delivery**, which has still never been observed from a rule. The sprint backlog item from 2026-08-08 is still open. `odoo19_dev`'s Telegram account has a token; the scratch database's does not.
4. **Clean up my probe leftovers in `odoo19_dev`** — posted invoice `INV/2026/00001` (id 25, 575.00) and partner *Overdue Probe Ltd* (id 348). Left alone because reversing posted accounting entries is not something to do unasked. It also consumed the first number of the 2026 invoice sequence.
5. **Unrelated, but it will keep appearing in the logs:** `midvex_l10n_tr_marketplace_foundry` and `midvex_l10n_tr_marketplace_trendyol` fail to load in `odoo19_dev` (missing dependency or manifest). Different repository.

### Two production prerequisites, neither verified on erp

- **A cron worker must be running.** Prompt delivery is an `ir.cron` trigger, and the queue itself is a cron. With `max_cron_threads = 0` nothing sends at all, triggered or not. Local config has 1.
- **The live account's channel code.** The 2026-08-08 entry recorded it as `1`, so no adapter resolves and every send fails. Unless that was fixed on erp directly, it still is.

### Exact next validation step

```bash
cd ~/Development/odoo19-dev && source .venv/bin/activate
python odoo/odoo-bin -c config/odoo.conf -d odoo19_dev --http-port=8099 --dev= \
  -u midvex_o_notification_foundry,midvex_o_notification_telegram,midvex_o_notification_business \
  --stop-after-init
```

Then, in the UI: set an audience on `rule_invoice_posted`, post a customer invoice, and confirm the message reaches `sent` within seconds — `SELECT state, create_date, sent_at FROM midvex_notification_message ORDER BY id DESC LIMIT 5;`. `sent_at - create_date` is the number that proves the delivery path end to end against the real Telegram API, which is the one thing this session measured only against a tokenless account.

## 2026-08-14 — The omnichannel pack, and WhatsApp as a real channel

### Objective

A 23-file omnichannel messaging specification pack appeared in `~/Projects/varsco_omnichannel_messaging_project/` on 2026-08-14, untracked and with no history. Its own merge map said it belonged in this repository. The ask was to review it and start building. Scope was agreed with the user as roadmap phases 0–2: freeze the contract here, then build WhatsApp as a working transport.

### Read

Root `AGENTS.md`, `~/Development/odoo19-dev/AGENTS.md`, the suite architecture, the foundry's PRD/architecture/data model/adapter contract, the Telegram implementation, `docs/SPRINT_BACKLOG.md`, and the whole 2026-08-01 → 2026-08-10 handoff log. Then all 23 pack files.

### Decisions — ADR-013 through ADR-018

Recorded in `docs/projects/notification_foundry/DECISIONS.md`, so only the surprising parts here.

**The pack is wrong about the frontend.** It says "headless Next.js" in the brief, the live chat spec, the API spec and an ADR. There is no Next.js VARS site on this machine. `Websites/varsco_com` is TanStack Start + Vite + React on Bun, Lovable-connected — its own `AGENTS.md` warns that commits sync back to the Lovable editor and history must not be rewritten. Its `WhatsAppWidget.tsx` is a nine-language `wa.me` deep-link popover that Odoo never sees, which makes it the shell phase 5 absorbs rather than something to replace. Corrected on merge with the user's agreement rather than carried forward. ADR-016.

**The pack proposes a second adapter registry.** It also says, in the same file, "do not invent an incompatible registry when reuse is possible." Reuse is possible. The contract is now the five methods `TelegramAdapter` already implements plus three optional additions with conservative defaults, so no existing adapter needs editing. The method-by-method mapping is in `conversation_foundry/ADAPTER_CONTRACT.md`. ADR-015.

**Model names get the `midvex.` prefix.** `conversation.thread` claims a generic name in a registry shared with `mail` and `im_livechat`. ADR-014.

**AGENTS.md contradicted the work.** It, `notification_foundry/PRD.md` and `notification_telegram/PRD.md` all list "inbound conversational commands beyond `/link`" as an explicit non-goal. Building inbound while that stood would have left the rules losing to the code, quietly. Superseded in writing, and narrowed rather than deleted: it still holds for the *notification* modules. ADR-018.

### Files changed

Two commits.

`4a57b7b docs:` — six new project directories under `docs/projects/`, ADR-013…018, `AGENTS.md` reading order and scope note, `PROJECT_INDEX_NOTIFICATION.md`, Sprints 4–7 appended to `SPRINT_BACKLOG.md`, a stale `README.md` fixed (it never mentioned `midvex_o_notification_business`), and `notification_whatsapp/API_RESEARCH.md` filled in.

`d2cb23d feat(whatsapp):` — `addons/midvex_o_notification_whatsapp/`, 23 files. Client, adapter, webhook controller, account extension, template mapping model, two fields on the message, one on the inbound event, views, security, channel data, 84-string Turkish catalogue, and 76 tests.

### API research

`notification_whatsapp/API_RESEARCH.md` was the blank template, which under this repo's channel-API rule blocks payload work. Verified against Meta's documentation on 2026-08-14 with URLs and dates recorded: Graph API v26.0 is latest (released 2026-07-29), v25.0 pinned as a per-account field with runway to 2028; System User tokens and their three scopes; both send payload shapes; `hub.challenge` verification and `X-Hub-Signature-256` over the raw body; inbound message and status envelopes; a thirty-entry error-code table mapped to the taxonomy; rate limits; and the 24-hour window.

The window's duration is cited from error code `131047`, not from the overview page — the overview names the window without stating how long it is. That is the kind of thing worth not re-deriving.

Also written: the credential onboarding and rotation runbook, because the module was built without credentials and somebody has to do those eight steps before a single message is delivered.

### Things worth not rediscovering

- **The inbound event model could not carry the dedupe key.** `external_id` looks like the obvious column, and for Telegram it holds the *chat* id — every message from one chat reuses it. A unique constraint there would have rejected the second message anybody ever sent the bot. `wa_event_key` is a separate column, NULL on Telegram rows, and Postgres treats NULLs as distinct.
- **The key is not the wamid alone.** One outbound message produces three status notifications, all naming it. Keying on the wamid would have accepted `sent` and silently rejected `delivered` and `read`, leaving every message stuck one rung down.
- **`read` arrives before `delivered`.** Routinely, not rarely. The ladder refuses to move backwards.
- **The signature covers bytes, not meaning.** Verifying against `json.dumps(parsed)` fails silently in the safe direction until a payload's key order differs, at which point every genuine webhook is rejected. There is a test that asserts re-serialized JSON does *not* verify.
- **Meta has no `setWebhook`.** The header's Register Webhook button now raises with an explanation rather than reporting success for a call it never made.
- **Searching a Json column with `like` was the first attempt** at matching a status to its message. Replaced with a stored computed `wa_message_id` — indexed, exact, and it leaves the foundry's `action_process` untouched.

### Verification

- **196 tests, 0 failed, 3 errors** on a fresh `odoo19_wa_final`. Up from 120.
- **The 3 errors are not mine.** A control run on `odoo19_wa_control` with this module *not installed* produced the identical three: `test_sale_and_invoice_templates_render`, `test_the_payment_template_renders`, `test_vendor_templates_render`, all failing to create an `account.move`/`account.payment` with no journal on a database with no chart of accounts. Environmental, and worth knowing before somebody spends an afternoon on it.
- Installed cleanly into `odoo19_dev`, backed up first to `backups/odoo19_dev_pre_whatsapp.dump`. Schema confirmed by hand: `wa_event_key` and its unique constraint, `wa_message_id`, `wa_delivery_status`, five account columns, the mapping table, the channel row.
- Secret scan clean over the new module and all of `docs/`.
- `odoo19_dev` still fails to load `midvex_l10n_tr_marketplace_foundry` and `_trendyol`. Unchanged, different repository, item 5 from the last entry.

### Risks and open questions

- **Nothing here has ever spoken to Meta.** No credentials exist yet. Live delivery, a genuine signed webhook, real statuses and long-term token behaviour are all unproven, and no amount of fixture testing changes that.
- **Inbound free text is stored and dropped.** It is deduped and acknowledged and nothing reads it, because `midvex_o_conversation_foundry` does not exist. That is the roadmap's phase-2 exit criterion exactly, but it means an inbound customer message currently produces a row and no reply. If a number goes live before phase 3, somebody must be watching Inbound Events by hand.
- **Inbound message events stay `processed = False`** for the same reason. Status events are marked processed on every path, including ones that change nothing, so they cannot accumulate as a false alarm against the runbook's "unprocessed events" check. Message events genuinely are unprocessed and show as such.
- **`v25.0` will age.** It is a field on the account, not a constant, so moving is a data change — but nothing reminds anyone. v25.0 is available until 2028-07-29.
- **The previous entry's items 2, 3 and 4 are still open**, untouched: audiences on the shipped business rules, a real end-to-end Telegram delivery that has still never been observed, and the probe leftovers in `odoo19_dev` (posted invoice `INV/2026/00001` id 25, partner *Overdue Probe Ltd* id 348). The two production prerequisites on `erp` are also still unverified, and both block WhatsApp exactly as they block Telegram: no cron worker means nothing sends at all, and the live account's channel code recorded as `1` means no adapter resolves.

### Migration

None. `midvex_o_notification_whatsapp` is new. Its two additions to `midvex.notification.message` are a stored compute and a nullable Selection; `wa_event_key` is nullable on a table that had zero rows in `odoo19_dev` and whose Telegram rows would be unaffected regardless.

### Exact next step

The module cannot be validated further without credentials. When they exist, work the eight-step onboarding in `docs/projects/notification_whatsapp/API_RESEARCH.md` against a **dedicated test number**, then:

```bash
cd ~/Development/odoo19-dev && source .venv/bin/activate
python odoo/odoo-bin -c config/odoo.conf -d odoo19_dev --http-port=8099 --dev= \
  -u midvex_o_notification_whatsapp --stop-after-init
```

Then in the UI: create a WhatsApp account, enter the three credentials yourself, press **Test Connection** — it reads the phone number node and messages nobody, so it is safe to run first. The one number that proves the path is what `SELECT state, wa_delivery_status, sent_at FROM midvex_notification_message ORDER BY id DESC LIMIT 5;` shows after a real send: `wa_delivery_status` reaching `delivered` means the outbound call, the webhook, the signature check and the status ladder all worked, which is the whole chain this session could only prove one fixture at a time.

Until then, the honest status is: built, tested against fixtures, and never once run against WhatsApp.

## 2026-08-14 (later) — Reading the WhatsApp module back, and what it turned up

### Objective

A review pass over the ~1,000 lines committed above, before anything depends on them. Three defects, all real, none found by the tests that already existed — which is the useful part.

### What the tests could not have caught

**Views load and render are different things.** A modifier referencing a field absent from the arch loads cleanly and fails when somebody opens the form. Checked by calling `get_views` for the account form, both template views and the message list; all render, and Odoo auto-added `channel_code` because the modifier referenced it. Worth doing again after any view change — the install log will not tell you.

### The three defects

**1. A stranger could turn a 403 into a 500.** `hmac.compare_digest` raises `TypeError` on a `str` containing any non-ASCII character. Both comparisons in the webhook take input somebody else controls — the `X-Hub-Signature-256` header, and the `hub.verify_token` query parameter — so one high byte produced an unhandled exception instead of a refusal.

The reason it matters is specific to this endpoint: **Meta retries a 500 and does not retry a 403.** An unauthenticated caller could therefore make the endpoint retry-storm itself by sending one malformed header. Fixed with `constant_time_equals`, which encodes to bytes first; `compare_digest` has no ASCII restriction on bytes and stays constant-time.

**2. A misconfigured record burned three retries and then lied about why.** Missing token, missing phone number ID and a recipient with no number were plain `UserError`, so the foundry's sensible default — retry an unclassified failure — applied to three things no retry can fix. Each spent 1, 5 and 25 minutes and then reported `failed`, indistinguishable from a provider outage.

`WhatsAppError` now carries `permanent=True` for pre-flight failures and they quarantine on the first attempt. This is the same principle as the Telegram adapter's `_PERMANENT_FRAGMENTS`, reached by a flag rather than by matching prose — these strings are ours, so there is no reason to pattern-match them.

**3. The template mapping model had no record rule.** It shipped with access rights, which say who may read the *model*, not which *rows*. A user in one company could read, and a manager could edit, another company's mappings — which name the provider templates that company had approved under its own WABA. The acceptance criteria say plainly that a view domain is not isolation; access rights are not either, and it is easy to conflate them when the ACL file is the only security file in the module.

### Verification

- **213 tests, 0 failed** on fresh `odoo19_wa_final2`, up from 196. WhatsApp's own count went 76 → 93.
- Same 3 pre-existing chart-of-accounts errors, unchanged.
- `odoo19_dev` updated to `19.0.1.0.1`; `rule_whatsapp_template_company` confirmed present in `ir_rule` by hand.
- Secret scan clean.

### Worth not rediscovering

- **Assert classification through the queue, not at the seam.** `parse_error` returning `retryable: False` is worth nothing unless `_handle_failure` acts on it. Four tests now drive real messages through `action_process` and assert the resulting `state`, which is how defect 2 was confirmed fixed rather than assumed.
- **The registry holds one adapter instance for the process lifetime.** Those queue tests stub `adapter.client.send_message` on the *registered* instance, so each restores it in a `finally`. A stub left behind follows the suite into every later test. The 2026-08-09 entry warned about this for `send_calls`; it applies to anything hung off a registered adapter.

### Still true, unchanged

Nothing here has spoken to Meta. No credentials. Inbound free text is stored, deduped, acknowledged and read by nothing. The previous entry's items 2–4 and both `erp` prerequisites are still open.

### Exact next step

Unchanged from the entry above: the eight-step onboarding in `docs/projects/notification_whatsapp/API_RESEARCH.md`, against a dedicated test number, then confirm `wa_delivery_status` reaches `delivered` on a real send.

One repository-level thing first, though: **everything above is local — nothing has been pushed.** Deliberately: pushing was offered and not taken up, so `main` is waiting.

No count is written here on purpose. The 2026-08-10 entry recorded "11 commits ahead" and that number was stale by the time anyone read it; writing one here would go stale the moment this entry was itself committed. Run it instead:

```bash
git rev-list --count origin/main..HEAD
```

## 2026-08-15 — Phase 3: somewhere to put what a customer says

### Objective

Build the Conversation Foundry. Until this, inbound free text was stored in an envelope and dropped — there was no thread, no identity, no assignment, no read state, nowhere for it to go.

### Two decisions settled before any code

Both had been flagged in `docs/projects/conversation_foundry/` as needing an ADR first, which turned out to be right: each of them changes what the module is.

**ADR-019 — one inbound envelope store, shared.** The webhook is already shared: Meta delivers a number's callbacks to exactly one URL, so `/notification/whatsapp/webhook/<id>` receives customer messages and delivery statuses through the same door and writes both before parsing either. A second table would mean that controller choosing which one an event belongs in at the moment it knows least, and would split the `wa_event_key` dedupe space in two — a redelivery landing in the other table would be accepted twice.

**ADR-020 — replies go out through the one delivery queue.** `AGENTS.md` is unambiguous that channel modules must not write their own queue, retry or log logic. A conversation foundry with its own drain would have been the largest violation of that rule in the repository, and a second implementation of the three things the 2026-08-09 and 2026-08-10 sessions spent their length getting right.

Extracting the machinery into a mixin shared by two queue tables is the more elegant shape and was rejected on risk: moving ~150 lines of a production delivery path guarded by 99 tests, in the same change that introduces five new models. One queue with a nullable recipient is a much smaller diff and leaves the mixin available later.

### The queue change, landed separately

`7afc033`, on its own so the delivery path was provably green before anything sat on it.

`recipient_id` is now optional, `destination_external_id` addresses a customer directly, and a computed `destination_key` resolves to whichever was given.

**The throttle now keys on that destination rather than on `recipient_id`, and that is a correction rather than an accommodation.** The provider limits how fast we may talk to one chat or one number; `recipient_id` was only ever a proxy for it. The proxy breaks completely the moment conversation replies share the queue — every one of them has no recipient, so keyed the old way they would all have shared a single empty key and paced each other. One customer's reply would have throttled every other customer's. There is a test for exactly that, and another for the flip side: a recipient and a raw destination naming the same address *do* throttle together, because the provider sees one chat whatever Odoo calls it.

Quiet hours are skipped when there is no recipient — not a special case, since quiet hours belong to a person who asked not to be woken and a customer never did. It also stops `_quiet_release_at`'s `ensure_one()` raising inside the cron and taking the rest of the batch with it.

### Things worth not rediscovering

- **A constrain listing two fields does not fire when a create names neither.** Odoo validates only the fields present in the write, so the "has a destination" check skipped exactly the case it existed to catch. It now triggers on the computed key, which is always present, while *checking* the two fields.
- **…and checking the key instead of the fields was itself wrong.** It refused a message to a recipient whose linking is unfinished. Addressed-to-somebody-we-cannot-yet-reach is not addressed-to-nobody: refusing at create leaves the failure with no row, no log and nothing in the queue for anyone to find. Both mistakes were made here in sequence; both are now pinned by tests.
- **The inbound status transition first read only `new` and `waiting_customer`.** So a customer replying to a thread already `open` — the ordinary case of an ongoing exchange — left `status` saying nothing was owed while `unanswered` said otherwise. Two fields disagreeing about the same fact is how an inbox filter starts hiding work.
- **`expand` is no longer a valid attribute on a search view's `<group>` in Odoo 19.** It fails at module load with a RelaxNG error pointing at the wrong line. The house pattern is bare `<filter>` elements after a `<separator/>`.
- **A view that loads is not a view that renders.** Checked again with `get_views` for every new view; a modifier naming a field absent from the arch passes install and fails when somebody opens the form.

### Verification

- **291 tests, 0 failed**, fresh `odoo19_p3_final2`. Up from 213. Conversation foundry 69; the foundry gained 11.
- Same 3 pre-existing chart-of-accounts errors, unchanged and independently confirmed earlier.
- Installed into `odoo19_dev`, backed up first to `backups/odoo19_dev_pre_conversation.dump`. Five tables, five record rules, `recipient_id` nullable and foundry at `19.0.1.6.0`, all confirmed by hand.
- Secret scan clean.

### Risks and open questions

- **No channel is wired to it.** The foundry is provider-neutral and tested against an in-memory fake, which is deliberate — but it means nothing real flows through it yet. `midvex_o_conversation_whatsapp` is the next step and is small: the webhook already parses inbound messages and already stores the envelope this now knows how to read.
- **The inbox has no compose box.** Replying is a service call (`queue_outbound`). The views list, filter, assign, resolve and reopen; typing a reply in the UI is phase 4.
- **`_compute_unanswered` depends on `message_ids.direction` and `create_date`.** It recomputes over a thread's whole message list. Fine at the volumes this will see for a long time, and worth remembering if a thread ever runs to thousands.
- Everything from the previous entries still stands: no Meta credentials, the old handoff's items 2–4, and both `erp` prerequisites.

### Migration

`19.0.1.6.0` backfills `destination_key`. A new stored computed column is populated on upgrade anyway, so it is belt and braces — it exists because a NULL key is invisible to the throttle's search, which would mean every historical row silently stopped counting toward the rate limit.

### Exact next step

Wire WhatsApp to the foundry. The pieces are all present:

```python
from odoo.addons.midvex_o_conversation_foundry.services import conversation

identity = conversation.ensure_identity(env, company, 'whatsapp', adapter.normalize_identity(sender))
thread   = conversation.ensure_thread(env, company, identity)
session  = conversation.open_session(env, thread, account, identity.normalized_identifier)
conversation.record_inbound(env, session, normalized_inbound_dto, inbound_event=event)
```

The webhook's `messages[]` branch is currently inert by design; that is where the four lines go. `statuses[]` should additionally call `conversation.apply_status`. Then the first milestone is one CRM bridge away.

Still local. `git rev-list --count origin/main..HEAD`.

## 2026-08-17 — Apps-list icons for the two conversation modules

Reported as "the conversation module doesn't have an icon". Cosmetic, and the
smaller of the two icon problems this repo has already hit.

### What was actually missing

The August 10 entry above records the distinction and it applies again, in the
other direction. There are two icons:

| Where | Comes from | conversation_foundry |
|---|---|---|
| Apps list card (Settings → Apps) | `static/description/icon.png` | ❌ absent — the placeholder |
| Home screen tile | `web_icon` on a root `ir.ui.menu` | n/a — has no root menu |

Last time the PNG existed and the `web_icon` did not. This time neither module
had a PNG at all. `midvex_o_conversation_foundry` and
`midvex_o_conversation_whatsapp` were the only conversation addons with no
`static/` directory whatsoever, so both cards drew Odoo's generic placeholder.

### What was not done, deliberately

No `web_icon`, no `application: True`, no re-parenting. "Conversations" is a
child of `menu_notification_root` by an explicit decision recorded in the
comment at the top of `conversation_menus.xml` — outgoing messages and incoming
messages are one area of the business to whoever uses them. A module with no
root menu has no tile, so there was nothing for a `web_icon` to attach to. The
user was offered the second-tile option and declined it.

### Files

- `addons/midvex_o_conversation_foundry/static/description/icon.svg` + `icon.png`
- `addons/midvex_o_conversation_whatsapp/static/description/icon.svg` + `icon.png`
- both `__manifest__.py`: `19.0.1.0.0` → `19.0.1.0.1`
- both channel `CHANGELOG.md`

Same rounded square, same `#5B4B9E → #3D3270` gradient as the notification
foundry, with two speech bubbles instead of the bell — inbound white, outbound
in the house accent `#F0663F`, and WhatsApp green `#25D366` on the connector.
The outbound bubble is drawn twice, once filled *and* stroked in the background
colour, so it cuts a clean gap where it overlaps the white one; stroking the
final shape shows the seam between the rectangle and its tail.

As with the foundry, `icon.svg` is the editable master and Odoo reads nothing
but the PNG. Re-render with:

```bash
inkscape --export-type=png --export-width=256 --export-height=256 \
  --export-filename=static/description/icon.png static/description/icon.svg
```

### Exact next step

Not validated in a database — this touches no Python, XML or data file, and the
version bumps are signalling only. `ir.module.module.icon` is set when the
module list is scanned, so the cards refresh on **Update Apps List** or a
restart; no `-u` is required. Confirm the two cards in Settings → Apps, then
return to the compose box in the inbox (phase 4), which is still the real open
item from the previous entry.

Still local. `git rev-list --count origin/main..HEAD`.
