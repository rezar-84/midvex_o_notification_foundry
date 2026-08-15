def migrate(cr, version):
    """Backfill destination_key on messages that predate it.

    A brand-new stored computed column *is* computed for existing rows on
    upgrade, unlike the stored related field in 19.0.1.1.0 whose column already
    existed — so strictly this is belt and braces.

    It is here because the cost of being wrong is asymmetric. If the compute
    did not run, every historical row would carry a NULL key, and the per
    destination throttle searches on exactly that: a NULL row is invisible to
    the search, so the rate limit would silently stop seeing anything that was
    sent before this upgrade. That is a limit quietly not being applied, which
    is the kind of thing nobody notices until a provider does.

    Written to touch only rows that need it, so re-running is free.
    """
    cr.execute("""
        UPDATE midvex_notification_message AS message
           SET destination_key = recipient.external_id
          FROM midvex_notification_recipient AS recipient
         WHERE message.recipient_id = recipient.id
           AND message.destination_key IS NULL
           AND recipient.external_id IS NOT NULL
    """)
    cr.execute("""
        UPDATE midvex_notification_message
           SET destination_key = destination_external_id
         WHERE destination_key IS NULL
           AND destination_external_id IS NOT NULL
    """)
