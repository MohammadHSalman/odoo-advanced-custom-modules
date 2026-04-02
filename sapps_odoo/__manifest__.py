# -*- coding: utf-8 -*-
{
    'name': "SAPPS - Odoo",

    'summary': """
        Integration solution for SAPPS's systems with the Syrian Ministry of Finance for tax compliance and reporting.
    """,

    'description': """
        This module provides a robust integration between SAPPS's financial systems and the Syrian Ministry of Finance.
        It facilitates the seamless exchange of tax-related data,
        ensuring accurate tax reporting and compliance with Syrian tax regulations.
        Designed to support businesses in maintaining tax compliance while improving operational efficiency and accuracy in tax reporting.
    """,

    'author': "Mohammad Haitham Salman From SAPPS Group",
    'website': "https://www.s-apps.io/",

    # Categories to filter modules in the listing
    # Check https://github.com/odoo/odoo/blob/15.0/odoo/addons/base/data/ir_module_category_data.xml
    # for the full list
    'category': 'Accounting/Accounting',
    'version': '18.2',

    # Dependencies required for this module to work correctly
    'depends': ['base', 'point_of_sale', 'account',  'pos_restaurant', 'sale'],

    # Path to module images
    'images': ["static/description/icon.png"],

    # Data files to be loaded
    'data': [
        'security/ir.model.access.csv',
        'security/security.xml',
        #'data/syrian_tax_information.xml',
        # 'data/sapps_info.xml',
        'report/report_invoices_details.xml',
        'report/report.xml',
        #'views/account_tax_view.xml',
        'views/connection_authentication_views.xml',
        'views/pos_config_views.xml',
        'views/pos_order_audit_view.xml',
        'views/pos_order_view.xml',
        'views/res_company_view.xml',
        'views/res_config_settings_views.xml',
        'views/send_bill_view.xml',
        'views/report_sale_order.xml',

    ],

    # Assets (CSS/JS) for the Point of Sale interface
    'assets': {
        'point_of_sale._assets_pos': [
            'sapps_odoo/static/src/js/**/*',
            'sapps_odoo/static/src/lip/**/*',
            'sapps_odoo/static/src/xml/**/*',
        ],
    },
}
