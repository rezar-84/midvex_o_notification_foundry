from odoo import SUPERUSER_ID, api


def migrate(cr, version):
    """Wire up rules that were created before rules could wire themselves.

    Until 19.0.1.2.0 the only thing that made a rule fire was a hand-written
    base.automation in the Telegram module's data file, covering crm.lead on
    create and nothing else. Rules created through the UI matched nothing and
    said nothing about it.

    Existing rules therefore have no automation_id, and any rule on another
    model — or on update — has no automation at all. _sync_automations()
    adopts the hand-written one where it fits rather than duplicating it, so
    this is safe to run on a database that already has it.
    """
    env = api.Environment(cr, SUPERUSER_ID, {})
    rules = env['midvex.notification.rule'].search([])
    if rules:
        rules._sync_automations()
