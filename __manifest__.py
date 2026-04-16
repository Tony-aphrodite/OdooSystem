{
    'name': 'Alquiler de Equipos',
    'version': '17.0.1.0.0',
    'category': 'Accounting',
    'summary': 'Gestión de alquiler de equipos con facturación recurrente y remesas SEPA',
    'description': """
        Módulo de gestión de alquiler de equipos:
        - Facturación automática mensual
        - Gestión de mandatos SEPA
        - Generación de remesas SEPA (pain.008)
        - Gestión de equipos y trazabilidad
    """,
    'author': 'Steve.C',
    'depends': [
        'base',
        'account',
        'contacts',
        'mail',
    ],
    'data': [
        'security/alquiler_security.xml',
        'security/ir.model.access.csv',
        'views/sepa_mandate_views.xml',
        'views/res_partner_views.xml',
        'views/sepa_remittance_views.xml',
        'views/recurring_invoice_views.xml',
        'views/dashboard_views.xml',
        'views/menu_views.xml',
        'data/sequence_data.xml',
        'data/company_data.xml',
        'data/cron_data.xml',
        'data/user_data.xml',
        'wizard/sepa_export_wizard_views.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'alquiler_equipos/static/src/css/dashboard.css',
        ],
    },
    'post_init_hook': '_post_init_generate_demo',
    'installable': True,
    'application': True,
    'license': 'LGPL-3',
}
