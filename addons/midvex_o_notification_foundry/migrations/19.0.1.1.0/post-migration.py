def migrate(cr, version):
    """Realign message.channel_code with the account it is sent through.

    channel_code was free text until 19.0.1.1.0, so rows exist carrying a code
    no adapter answers to — production has messages coded '1', which fail at
    send time with "No notification adapter is installed for channel 1".

    Making the field a stored related does not fix them on its own: Odoo only
    computes a stored related field for rows that are marked for recomputation,
    and an existing populated column is not. That was verified on a real
    upgrade before this file was written — a poisoned row survived it
    untouched.

    Note this repairs the message against its account. If the *account's*
    channel is itself miscoded, this faithfully copies the wrong code, and the
    channel record has to be corrected first. See docs/HANDOFF_LOG.md.
    """
    cr.execute("""
        UPDATE midvex_notification_message AS message
           SET channel_code = account.channel_code
          FROM midvex_notification_account AS account
         WHERE message.account_id = account.id
           AND message.channel_code IS DISTINCT FROM account.channel_code
    """)
