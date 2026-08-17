{
    'name': 'Midvex Conversation Foundry',
    'version': '19.0.1.0.1',
    'summary': 'Provider-neutral two-way customer conversations for Odoo',
    'category': 'Productivity',
    'author': 'Midvex',
    'license': 'GPL-3',
    'depends': ['midvex_o_notification_foundry'],
    'data': [
        'security/conversation_security.xml',
        'security/ir.model.access.csv',
        'views/conversation_views.xml',
        'views/conversation_menus.xml',
    ],
    'installable': True,
    'application': False,
}
