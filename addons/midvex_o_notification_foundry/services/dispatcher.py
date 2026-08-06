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
        for user in users:
            for channel in rule.channel_ids:
                recipient = Recipient.search([
                    ('user_id', '=', user.id),
                    ('channel_code', '=', channel.code),
                    ('state', '=', 'linked'),
                ], limit=1)
                if not recipient:
                    continue
                account = Account.search([
                    ('channel_code', '=', channel.code),
                    ('company_id', '=', company_id),
                    ('active', '=', True),
                    ('state', '=', 'connected'),
                ], limit=1)
                if not account:
                    continue
                idempotency_key = hashlib.sha256(
                    f'{rule.id}-{model_name}-{record.id}-{user.id}-{channel.code}'.encode()
                ).hexdigest()
                if Message.search([('idempotency_key', '=', idempotency_key)], limit=1):
                    continue
                rendered = rule.template_id.render(record)
                created |= Message.create({
                    'rule_id': rule.id,
                    'recipient_id': recipient.id,
                    'account_id': account.id,
                    'channel_code': channel.code,
                    'res_model': model_name,
                    'res_id': record.id,
                    'subject': rendered.get('subject'),
                    'body': rendered.get('body'),
                    'idempotency_key': idempotency_key,
                })
    return created
