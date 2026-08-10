{
    'name': 'Midvex Notification Business Events',
    'version': '19.0.1.2.0',
    'summary': 'Ready-made CRM, Sales and Invoicing notification templates and rules',
    'category': 'Productivity',
    'author': 'Midvex',
    'license': 'GPL-3',
    # Kept out of the Telegram adapter on purpose: these templates need sale
    # and account, and an adapter should not drag Invoicing onto an install
    # that only wants Telegram alerts.
    'depends': ['midvex_o_notification_telegram', 'crm', 'sale', 'account'],
    'data': [
        'data/crm_templates.xml',
        'data/sale_templates.xml',
        'data/account_templates.xml',
        'data/server_actions.xml',
    ],
    'installable': True,
}
