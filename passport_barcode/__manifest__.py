# -*- coding: utf-8 -*-
{
    'name': "passport_barcode",

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
    'depends': ['base', 'sahara_planet'],

    # always loaded
    'data': [
        # 'security/ir.model.access.csv',
        'views/res_partner_views.xml',
    ],
    # only loaded in demonstration mode
    'demo': [
        'demo/demo.xml',
    ],
}
