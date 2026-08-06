{
    'name': 'Midvex Notification Foundry',
    'version': '19.0.1.0.0',
    'summary': 'Shared notification channels, accounts, templates, rules, queue, logs and dashboard',
    'category': 'Productivity',
    'author': 'Midvex',
    'license': 'GPL-3',
    'depends': ['base', 'mail'],
    'data': [
        'security/notification_security.xml',
        'security/ir.model.access.csv',
        'data/notification_cron.xml',
        'views/notification_views.xml',
        'views/notification_menus.xml',
    ],
    'application': True,
    'installable': True,
}
