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


def enqueue_event(env, model_name, record, event_code):
    trigger = 'on_create' if event_code == 'created' else 'on_write'
    rules = env['midvex.notification.rule'].search([
        ('active', '=', True),
        ('model_id.model', '=', model_name),
        ('trigger', '=', trigger),
    ])
    Message = env['midvex.notification.message']
    Recipient = env['midvex.notification.recipient']
    Account = env['midvex.notification.account']
    created = Message
    company_id = _record_company_id(record, env)
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
                    f'{rule.id}-{model_name}-{record.id}-{token}-{channel.code}'.encode()
                ).hexdigest()
                if Message.search([('idempotency_key', '=', idempotency_key)], limit=1):
                    continue
                rendered = rule.template_id.render(record)
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
