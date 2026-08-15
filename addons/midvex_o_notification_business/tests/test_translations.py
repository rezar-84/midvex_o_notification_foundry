import os

from odoo.modules.module import get_module_path
from odoo.tests.common import TransactionCase

MODULES = (
    'midvex_o_notification_foundry',
    'midvex_o_notification_telegram',
    'midvex_o_notification_business',
    'midvex_o_notification_whatsapp',
    'midvex_o_conversation_foundry',
)


def _entries(path):
    """Yield (msgid, msgstr) pairs from a .po file.

    Deliberately not polib: it is not a hard dependency of Odoo, and the only
    thing being asked here is whether a msgstr is empty. Continuation lines
    matter - a long body is written as several quoted lines - so they are
    folded onto whichever of the two the parser is currently inside.
    """
    msgid = msgstr = None
    current = None
    with open(path, encoding='utf-8') as handle:
        for raw in handle:
            line = raw.strip()
            if line.startswith('msgid '):
                if msgid is not None:
                    yield msgid, msgstr or ''
                msgid, msgstr, current = line[6:].strip('"'), '', 'id'
            elif line.startswith('msgstr '):
                msgstr, current = line[7:].strip('"'), 'str'
            elif line.startswith('"') and current == 'id':
                msgid += line.strip('"')
            elif line.startswith('"') and current == 'str':
                msgstr += line.strip('"')
    if msgid is not None:
        yield msgid, msgstr or ''


class TestTurkishCatalogues(TransactionCase):
    """A half-finished catalogue is invisible at runtime: an empty msgstr falls
    back to English, so the page simply looks untranslated in places nobody
    happened to open."""

    def _catalogue(self, module):
        """The module's tr.po path, or None when the module is not on the addons path.

        midvex_o_notification_whatsapp is checked here but is not a dependency
        of this module — the four addons live in one repository and are always
        deployed together, and get_module_path reads the addons path rather than
        the installed set. Returning None rather than raising keeps a missing
        sibling from failing a test that is about translation quality.
        """
        root = get_module_path(module)
        return os.path.join(root, 'i18n', 'tr.po') if root else None

    def test_every_module_ships_a_turkish_catalogue(self):
        for module in MODULES:
            path = self._catalogue(module)
            if path is None:
                continue
            self.assertTrue(os.path.exists(path), '%s has no Turkish catalogue' % module)

    def test_no_string_is_left_untranslated(self):
        for module in MODULES:
            path = self._catalogue(module)
            if path is None or not os.path.exists(path):
                continue
            # The header entry is the one with an empty msgid, and its msgstr
            # holds the PO metadata rather than a translation.
            missing = [msgid for msgid, msgstr in _entries(path) if msgid and not msgstr]
            self.assertFalse(
                missing,
                '%s/i18n/tr.po leaves %d string(s) untranslated, starting with: %s'
                % (module, len(missing), missing[:5]))
