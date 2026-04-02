{
    'name': 'Customer Enhancements',
    'version': '18.0.1.0.0',
    'depends': ['base', 'contacts', 'mail', 'account'],
    'author': 'Mohammad Haitham Salman',
    'summary': 'Custom enhancements and modifications for customer records',
    'description': """
        This module provides custom enhancements and modifications
        to customer (contact) records, including additional fields,
        business logic, and UI improvements.
    """,
    'data': [
        # 'security/ir.model.access.csv',
        # 'views/res_partner_views.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
    'license': 'LGPL-3',
}
