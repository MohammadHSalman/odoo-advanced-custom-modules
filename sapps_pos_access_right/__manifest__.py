# -*- coding: utf-8 -*-
{
    'name': "Sapps POS Access Right",

    'summary': 'To Restrict POS features for User',
    'description': 'This app allows you to enable or disable POS features '
                   'depending on the access rights granted to the User',

    "author": "Mohammad Haitham Salman From SAPPS LLC",
    "website": "https://www.s-apps.io/",
    'company': 'SAPPS LLC',

    # Categories can be used to filter modules in modules listing
    # Check https://github.com/odoo/odoo/blob/16.0/odoo/addons/base/data/ir_module_category_data.xml
    # for the full list
    "category": 'Point of Sale',
    'version': '17.0',

    # any module necessary for this one to work correctly
    'depends': ['base', 'point_of_sale', 'pos_discount'],

    # always loaded
    'data': [
        # 'security/ir.model.access.csv',
        'views/views.xml',
        'views/templates.xml',
    ],

}
