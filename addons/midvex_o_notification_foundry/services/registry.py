from odoo.exceptions import UserError

_ADAPTERS = {}


def register_adapter(adapter_class):
    _ADAPTERS[adapter_class.channel_code] = adapter_class()
    return adapter_class


def available_adapter_codes():
    """Codes of the adapters actually registered by installed modules.

    Drives the channel Code selection, so the field can only offer values that
    get_adapter() will resolve. A free-text code silently produced a channel
    nothing could send through: the dispatcher copies it onto every message and
    the mismatch only surfaced at delivery time.
    """
    return sorted(_ADAPTERS)


def get_adapter(channel_code):
    adapter = _ADAPTERS.get(channel_code)
    if not adapter:
        raise UserError('No notification adapter is installed for channel %s.' % channel_code)
    return adapter


def unregister_adapter(channel_code):
    _ADAPTERS.pop(channel_code, None)
