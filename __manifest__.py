{
    'name': 'Odoo OAuth',
    'version': '1.0',
    'category': 'Tools',
    'summary': 'OAuth token management for Odoo REST API',
    'description': """
        This module provides OAuth token management functionality for Odoo REST API.
        Features:
        - Generate access and refresh tokens
        - Token refresh mechanism
        - Secure token storage
        - Configurable token expiration
        - Protected API endpoints
    """,
    'author': 'Your Company',
    'website': 'https://www.yourcompany.com',
    'depends': ['base', 'web'],
    'data': [
        'security/ir.model.access.csv',
        'views/oauth_config_views.xml',
        'views/menu_views.xml',
    ],
    'assets': {},
    'installable': True,
    'application': True,
    'auto_install': False,
    'license': 'LGPL-3',
} 