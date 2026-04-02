# -*- coding: utf-8 -*-
{
    'name': "sahara_planet",

    'summary': """
        This module for integration with planet""",

    'description': """
        This module for Planet integration for customers is tax free
    """,

    'author': "Mohammad Salman in S-apps",
    'website': "https://www.s-apps.io/",

    # Categories can be used to filter modules in modules listing
    # Check https://github.com/odoo/odoo/blob/15.0/odoo/addons/base/data/ir_module_category_data.xml
    # for the full list
    'category': 'Uncategorized',
    'version': '0.1',

    # any module necessary for this one to work correctly
    'depends': ['base', 'point_of_sale', 'account', 'sahara'],

    # always loaded
    'data': [
        'security/ir.model.access.csv',
        'views/connection_authentication_views.xml',
        'views/res_partner_views.xml',
        'views/pos_config_views.xml',
        'views/pos_order_views.xml',
        'views/qr_code_views.xml',
        'report/cousto_header_and_footer.xml',
        'report/stock_report_views.xml',
    ],
    # only loaded in demonstration mode
    'assets': {
        'web.assets_backend': [
            'sahara_planet/static/src/js/AddTaxFree.js',
            'sahara_planet/static/src/js/TaxFreePos.js',
            'sahara_planet/static/src/js/SendAndRefund.js',
        ],
        'web.assets_qweb': [
            'sahara_planet/static/src/xml/TaxRefundTag.xml',
        ],
        "point_of_sale.assets": [
            "sahara_planet/static/src/css/*",
        ],
    },
}
