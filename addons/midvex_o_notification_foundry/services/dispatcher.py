import ast
import hashlib

from odoo import _
from odoo.exceptions import ValidationError


def _match_domain(record, domain_str):
    if not domain_str:
        return True
    try:
        domain = ast.literal_eval(domain_str)
    except (ValueError, SyntaxError) as error:
        raise ValidationError(_('Invalid trigger domain: %s') % error)
    return bool(record.filtered_domain(domain))


def _record_company_id(record, env):
    if 'company_id' in record._fields and record.company_id:
        return record.company_id.id
    return env.company.id


_TRIGGERS = {'created': 'on_create', 'updated': 'on_write', 'scheduled': 'on_schedule'}


def enqueue_event(env, model_name, record, event_code, rule_id=None):
    trigger = _TRIGGERS.get(event_code, 'on_write')
    domain = [
        ('active', '=', True),
        ('model_id.model', '=', model_name),
        ('trigger', '=', trigger),
    ]
    # A scheduled rule owns its automation and names itself in the call, so it
    # must not drag its siblings in: "due soon" and "overdue" watch the same
    # model with overlapping domains, and without this every run of either
    # would enqueue both.
    if rule_id:
        domain.append(('id', '=', rule_id))
    rules = env['midvex.notification.rule'].search(domain)
    Message = env['midvex.notification.message']
    Recipient = env['midvex.notification.recipient']
    Account = env['midvex.notification.account']
    created = Message
    company_id = _record_company_id(record, env)
    # An on_create rule fires once per record, so the record id alone makes the
    # event unique. An on_write rule fires on every change, and without
    # something that varies per change every one of them collapses onto the
    # first key: the record would notify once, ever, and then dedupe itself
    # into silence. write_date is that discriminator, and it is deliberately
    # absent for on_create so those keys stay byte-identical to the ones
    # already in the table.
    #
    # A scheduled rule gets a constant instead, so it notifies a given record
    # once and never again. That matches base.automation's own semantics - its
    # cron fires each record once, as its date crosses the window - and means
    # an automation recreated with a reset last_run cannot re-send anything.
    if trigger == 'on_create':
        occurrence = ''
    elif trigger == 'on_schedule':
        occurrence = '-sched'
    else:
        occurrence = '-%s' % record.write_date
    for rule in rules:
        if not _match_domain(record, rule.trigger_domain):
            continue
        users = rule.audience_user_ids | rule.audience_group_ids.all_user_ids
        for channel in rule.channel_ids:
            account = Account.search([
                ('channel_code', '=', channel.code),
                ('company_id', '=', company_id),
                ('active', '=', True),
                ('state', '=', 'connected'),
            ], limit=1)
            if not account:
                continue
            for recipient, token in _targets(Recipient, rule, users, channel):
                # The token, not the recipient id, keys idempotency: for a user
                # it stays the user id, which is the format already written to
                # every existing row. Keying on the recipient instead would
                # make every notification ever delivered look new and re-send.
                idempotency_key = hashlib.sha256(
                    f'{rule.id}-{model_name}-{record.id}{occurrence}-{token}-{channel.code}'.encode()
                ).hexdigest()
                if Message.search([('idempotency_key', '=', idempotency_key)], limit=1):
                    continue
                # Rendered per recipient, in the recipient's language. Template
                # subjects and bodies are translatable, but the environment
                # here belongs to whoever saved the record - so without this a
                # Turkish colleague's alert arrived in English purely because
                # an English-speaking user happened to trigger it. Group chats
                # have no user to ask (see the kind constraint on recipients),
                # so they keep the acting environment's language.
                rendered = _render_for(rule.template_id, record, recipient)
                created |= Message.create({
                    'rule_id': rule.id,
                    'recipient_id': recipient.id,
                    'account_id': account.id,
                    # channel_code is not set here: it is now related to the
                    # account, and writing through a related field would edit
                    # the account's channel rather than this message.
                    'res_model': model_name,
                    'res_id': record.id,
                    'subject': rendered.get('subject'),
                    'body': rendered.get('body'),
                    'idempotency_key': idempotency_key,
                })
    return created


def _render_for(template, record, recipient):
    """Render a template in the recipient's language.

    Putting the language on the *template* is enough to translate the record's
    own fields too: render() resolves placeholders through mail.render.mixin,
    which re-browses the record in the template's environment. A line like
    {{ object.stage_id.name }} therefore comes back Turkish as well, rather
    than leaving a translated sentence wrapped around an English stage.
    """
    lang = recipient.user_id.lang
    if not lang:
        return template.render(record)
    return template.with_context(lang=lang).render(record)


def _targets(Recipient, rule, users, channel):
    """Every (recipient, idempotency token) this rule delivers to on a channel.

    Two kinds, resolved differently: audience users are looked up to find the
    link they own, while group chats are already the destination and are named
    on the rule itself.
    """
    for user in users:
        recipient = Recipient.search([
            ('user_id', '=', user.id),
            ('channel_code', '=', channel.code),
            ('state', '=', 'linked'),
            # Muted is a pause, so nothing is enqueued at all rather than
            # queued and held: a burst of alerts should not arrive the moment
            # someone unmutes.
            ('muted', '=', False),
        ], limit=1)
        if recipient:
            yield recipient, str(user.id)

    # Archived chats never appear here at all — Odoo drops inactive records
    # from relational reads — so archiving one is a working off switch.
    for recipient in rule.audience_recipient_ids:
        if (recipient.channel_code == channel.code
                and recipient.state == 'linked' and not recipient.muted):
            yield recipient, 'chat%s' % recipient.id
