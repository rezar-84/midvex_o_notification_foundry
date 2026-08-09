{
    'name': 'Midvex Notification Foundry',
    'version': '19.0.1.2.0',
    'summary': 'Shared notification channels, accounts, templates, rules, queue, logs and dashboard',
    'category': 'Productivity',
    'author': 'Midvex',
    'license': 'GPL-3',
    # base_automation: notification rules create and maintain their own
    # base.automation records, which is what actually makes them fire.
    'depends': ['base', 'mail', 'base_automation'],
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
