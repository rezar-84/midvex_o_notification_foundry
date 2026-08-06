def ensure_channel(env, code, name=None):
    channel = env['midvex.notification.channel'].search([('code', '=', code)], limit=1)
    if channel:
        return channel
    return env['midvex.notification.channel'].create({'name': name or code.title(), 'code': code})
