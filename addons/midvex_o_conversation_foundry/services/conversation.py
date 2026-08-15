"""The conversation service.

Adapters and bridges call these functions; they do not `create()` on the models
directly. That is not ceremony — it is the seam that keeps the company
invariant, the state machine and the audit trail in one enforceable place
instead of re-implemented slightly differently by each channel.

A channel module's job is to normalize its provider's payload into the DTOs
described in `docs/projects/conversation_foundry/ADAPTER_CONTRACT.md` and hand
them here. Nothing below knows what WhatsApp is.
"""

import logging
import uuid

from odoo import _, fields
from odoo.exceptions import UserError, ValidationError

_logger = logging.getLogger(__name__)


def new_correlation_id():
    """An id to tie an envelope to the log lines it produces.

    The runbook tells people to search the logs by correlation id when a
    message goes missing, so one has to exist before anything is logged.
    """
    return uuid.uuid4().hex


def _normalized_message_type(Message, provider_type):
    """A value the message_type Selection can actually hold.

    Read off the field rather than hard-coded, so a channel module that adds a
    type does not have to remember to update a list here as well.
    """
    known = dict(Message._fields['message_type'].selection)
    return provider_type if provider_type in known else 'other'


def ensure_identity(env, company, identity_type, normalized_identifier,
                    display_identifier=None, provider_identifier=None):
    return env['midvex.conversation.identity'].find_or_create(
        company, identity_type, normalized_identifier,
        display_identifier=display_identifier, provider_identifier=provider_identifier)


def ensure_thread(env, company, identity, channel_code=None, subject=None):
    """The live thread for this person, or a new one.

    "Live" excludes resolved and archived deliberately: a customer coming back
    a month later about something else should not land inside a closed
    conversation about something different. A customer replying *within* a
    resolved thread is a different path — `record_inbound` reopens the thread
    the message actually arrived on.
    """
    Thread = env['midvex.conversation.thread'].sudo()
    thread = Thread.search([
        ('company_id', '=', company.id),
        ('identity_id', '=', identity.id),
        ('status', 'in', ['new', 'open', 'waiting_customer', 'waiting_agent']),
    ], order='last_message_at desc, id desc', limit=1)
    if thread:
        return thread

    return Thread.create({
        'name': subject or (identity.display_identifier or identity.normalized_identifier),
        'company_id': company.id,
        'identity_id': identity.id,
        'first_channel_code': channel_code or False,
    })


def open_session(env, thread, account, external_recipient_id,
                 external_session_id=None, metadata=None):
    """The open session for this thread on this account, or a new one.

    Reused rather than created per message: a session is the leg, not the
    exchange. Creating one each time would make the thread's history look like
    a customer who switched channel repeatedly.
    """
    if not external_recipient_id:
        raise ValidationError(_('A session needs an address to reply to.'))

    Session = env['midvex.conversation.session'].sudo()
    session = Session.search([
        ('thread_id', '=', thread.id),
        ('account_id', '=', account.id),
        ('state', '=', 'open'),
    ], limit=1)
    if session:
        if session.external_recipient_id != external_recipient_id:
            # The same person on the same account cannot have two addresses.
            # If this ever fires, something upstream failed to normalize.
            _logger.warning(
                'Conversation session %s already replies to a different address; '
                'leaving it alone.', session.id)
        return session

    return Session.create({
        'thread_id': thread.id,
        'channel_code': account.sudo().channel_code,
        'account_id': account.id,
        'external_recipient_id': external_recipient_id,
        'external_session_id': external_session_id or False,
        'metadata_json': metadata or {},
    })


def record_inbound(env, session, inbound, inbound_event=None):
    """File something a customer said.

    `inbound` is the normalized inbound DTO. Idempotent on the provider's
    message id: a redelivered webhook returns the message already recorded
    rather than a second copy of it, because the provider retries and we
    promised FR-007 it would not duplicate anything.
    """
    Message = env['midvex.conversation.message'].sudo()
    provider_message_id = inbound.get('external_message_id')

    if provider_message_id:
        existing = Message.search([
            ('session_id', '=', session.id),
            ('provider_message_id', '=', provider_message_id),
        ], limit=1)
        if existing:
            return existing

    thread = session.thread_id
    when = inbound.get('timestamp') or fields.Datetime.now()
    provider_type = inbound.get('message_type') or 'text'
    message = Message.create({
        'thread_id': thread.id,
        'session_id': session.id,
        'direction': 'inbound',
        # Coerced here rather than trusted from the channel. Providers invent
        # message types — WhatsApp alone sends stickers, reactions and orders —
        # and a Selection cannot hold a value it has never heard of. Left to the
        # ORM this raises, which would crash the webhook on a sticker and lose
        # every message batched alongside it.
        'message_type': _normalized_message_type(Message, provider_type),
        'provider_message_type': provider_type,
        'body': inbound.get('body') or False,
        'original_language': inbound.get('language_hint') or False,
        'provider_message_id': provider_message_id or False,
        # Inbound is terminal on arrival. It did not travel through our queue,
        # so there is no ladder for it to climb.
        'state': 'delivered',
        'origin': 'provider',
    })

    if not thread.language_code and inbound.get('language_hint'):
        thread.write({'language_code': inbound['language_hint']})
    session._touch(when)
    thread._touch(channel_code=session.channel_code, direction='inbound', when=when)

    if inbound_event:
        inbound_event.sudo().write({
            'conversation_thread_id': thread.id,
            'conversation_message_id': message.id,
            'processing_state': 'processed',
            'processed': True,
            'processed_at': fields.Datetime.now(),
        })
    return message


def queue_outbound(env, session, body, author=None, message_type='text',
                   origin='odoo', template_code=None, generated_by_ai=False):
    """Say something to the customer.

    Writes the durable message, then raises a delivery job in the notification
    foundry's queue and links the two. There is one queue in this platform, and
    this is a caller of it rather than a second one — retry, backoff, rate
    limiting and delivery logging all come from there. See ADR-020.
    """
    if session.state != 'open':
        raise UserError(_('This conversation channel is closed; reopen it to reply.'))
    if not (body or '').strip():
        raise UserError(_('An empty message cannot be sent.'))
    # Channel policy, asked before anything is written. A WhatsApp session
    # whose 24-hour window has closed refuses here rather than queueing a
    # message the provider will reject with 131047 — which would leave a
    # failed reply in the thread and an agent wondering what they did wrong.
    session.check_outbound_allowed(message_type)

    thread = session.thread_id
    Message = env['midvex.conversation.message'].sudo()
    message = Message.create({
        'thread_id': thread.id,
        'session_id': session.id,
        'direction': 'outbound',
        'message_type': message_type,
        'body': body,
        'author_user_id': (author or env.user).id,
        'origin': origin,
        'generated_by_ai': generated_by_ai,
        'state': 'queued',
    })

    delivery = env['midvex.notification.message'].sudo().create({
        'name': _('Conversation reply'),
        'account_id': session.account_id.id,
        'destination_external_id': session.external_recipient_id,
        'body': body,
        'res_model': 'midvex.conversation.thread',
        'res_id': thread.id,
        'idempotency_key': 'conversation-message-%s' % message.id,
    })
    message.write({'delivery_id': delivery.id, 'state': 'submitted'})

    session._touch()
    thread._touch(channel_code=session.channel_code, direction='outbound')

    # Same trigger the dispatcher uses, so a reply goes out in seconds rather
    # than waiting for the cron's own interval. ADR-012.
    env['midvex.notification.message']._trigger_queue()
    return message


def add_internal_note(env, thread, body, author=None):
    """A note for colleagues, which never reaches the customer.

    No session, therefore no delivery job, therefore nothing that could
    accidentally be sent. That is enforced by the model: a message with a
    customer-facing direction must have a session, and this one does not.
    """
    if not (body or '').strip():
        raise UserError(_('An empty note cannot be saved.'))
    return env['midvex.conversation.message'].sudo().create({
        'thread_id': thread.id,
        'direction': 'internal',
        'message_type': 'text',
        'body': body,
        'author_user_id': (author or env.user).id,
        'origin': 'odoo',
        'state': 'delivered',
    })


def apply_status(env, account, provider_message_id, status, when=None,
                 error_code=None, safe_message=None):
    """Move an outbound message along the delivery ladder.

    Matched on the provider's id scoped to the account, so one company's status
    event can never touch another's message. A status for an id this database
    never sent is normal — a shared number, a pruned row — and returns nothing
    rather than raising.
    """
    if not provider_message_id or not status:
        return env['midvex.conversation.message']

    message = env['midvex.conversation.message'].sudo().search([
        ('provider_message_id', '=', provider_message_id),
        ('session_id.account_id', '=', account.id),
    ], limit=1)
    if not message:
        return env['midvex.conversation.message']

    if status == 'failed':
        message._apply_failure(error_code=error_code, safe_message=safe_message, when=when)
    else:
        message._apply_delivery_state(status, when=when)
    return message


def link_delivery_result(env, delivery, provider_message_id):
    """Copy the provider's id onto the conversation message once the send lands.

    Kept here rather than in the queue because the notification foundry must
    not know that conversations exist. It hands back a result; this reads it.
    """
    message = env['midvex.conversation.message'].sudo().search(
        [('delivery_id', '=', delivery.id)], limit=1)
    if not message or not provider_message_id:
        return message
    message.write({'provider_message_id': provider_message_id})
    message._apply_delivery_state('sent')
    return message


def assign(env, thread, user, actor=None, reason=None):
    return thread.action_assign(user, actor=actor, reason=reason)


def resolve(env, thread):
    return thread.action_resolve()


def reopen(env, thread):
    return thread.action_reopen()
