# -*- coding: utf-8 -*-
{
    'name': "pos_layout",

    'summary': """
        Customize this module to change the look of the POS interface""",

    'description': """
        Customize this module to change the shape of the POS interface to suit the customer's request,
        as the request section has been expanded and the location of the control buttons has been changed
    """,

    'author': "S-apps",
    'website': "https://www.s-apps.io/",

    # Categories can be used to filter modules in modules listing
    # Check https://github.com/odoo/odoo/blob/15.0/odoo/addons/base/data/ir_module_category_data.xml
    # for the full list
    'category': 'Uncategorized',
    'version': '0.1',

    # any module necessary for this one to work correctly
    'depends': ['base', 'point_of_sale'],
    "images": ["static/description/icon.png"],
    # always loaded
    'data': [
        # 'security/ir.model.access.csv',
        'views/views.xml',
        'views/templates.xml',
    ],
    # only loaded in demonstration mode
    'demo': [
        'demo/demo.xml',
    ],
    "assets": {
        "point_of_sale.assets": [
            "pos_layout/static/src/scss/*",
        ],
        "web.assets_qweb": [
            "pos_layout/static/src/xml/*",
        ]
    }
}
