{
    'name': 'Midvex WhatsApp Notifications',
    'version': '19.0.1.1.0',
    'summary': 'WhatsApp Cloud API adapter for Midvex Notification Foundry',
    'category': 'Productivity',
    'author': 'Midvex',
    'license': 'GPL-3',
    'depends': ['midvex_o_notification_foundry'],
    'data': [
        'security/ir.model.access.csv',
        'security/whatsapp_security.xml',
        'data/whatsapp_channel.xml',
        'views/whatsapp_views.xml',
        'views/res_config_settings_views.xml',
    ],
    'installable': True,
}
