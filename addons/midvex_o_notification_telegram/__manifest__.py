{
    'name': 'Midvex Telegram Notifications',
    'version': '19.0.1.0.0',
    'summary': 'Telegram adapter for Midvex Notification Foundry',
    'category': 'Productivity',
    'author': 'Midvex',
    'license': 'GPL-3',
    'depends': ['midvex_o_notification_foundry', 'base_automation', 'crm'],
    'data': [
        'data/telegram_channel.xml',
        'data/notification_automation.xml',
    ],
    'installable': True,
}
