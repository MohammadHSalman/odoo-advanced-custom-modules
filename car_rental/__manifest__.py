# -*- coding: utf-8 -*-
{
    'name': "car_rental",

    'summary': """
        Short (1 phrase/line) summary of the module's purpose, used as
        subtitle on modules listing or apps.openerp.com""",

    'description': """
        Long description of module's purpose
    """,

    'author': "Mohammad Haitham Salman",
    'website': "http://www.yourcompany.com",

    # MHAZAS
    # Categories can be used to filter modules in modules listing
    # Check https://github.com/odoo/odoo/blob/15.0/odoo/addons/base/data/ir_module_category_data.xml
    # for the full list
    'category': 'Uncategorized',
    'version': '17.1',

    # any module necessary for this one to work correctly
    'depends': ['base', 'vehicle_rental'],

    # always loaded
    'data': [
        'security/ir.model.access.csv',
        'views/res_partner_views.xml',
        'views/vehicle_contract_views.xml',
        'views/fleet_vehicle_views.xml',
        'views/account_move_views.xml',
        'views/res_config_settings_views.xml',
        'views/res_company_views.xml',
        'views/booking_type_view.xml',
        'views/fuel_mng_view.xml',
        'views/fine_view.xml',
        'views/car_replacement_views.xml',
        'views/location_car.xml',
        'views/res_users_views.xml',
        'wizard/check_in_wizard_views.xml',
        # 'wizard/car_replacement_wizard_views.xml',
    ],
    # only loaded in demonstration mode
    'demo': [
        'demo/demo.xml',
    ],
}
