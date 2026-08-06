from odoo.exceptions import UserError

_ADAPTERS = {}


def register_adapter(adapter_class):
    _ADAPTERS[adapter_class.channel_code] = adapter_class()
    return adapter_class


def get_adapter(channel_code):
    adapter = _ADAPTERS.get(channel_code)
    if not adapter:
        raise UserError('No notification adapter is installed for channel %s.' % channel_code)
    return adapter


def unregister_adapter(channel_code):
    _ADAPTERS.pop(channel_code, None)
