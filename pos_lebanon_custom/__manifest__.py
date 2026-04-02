{
    'name': 'POS Multi-Currency Lebanon',
    'version': '18.0.1.0.5',
    'category': 'Point of Sale',
    'summary': 'Show dual currency remaining balance, detailed reports, and force mixed currency acceptance',
    'depends': ['point_of_sale'],
    'data': [
        'views/report_saledetails.xml',
    ],
    'assets': {
        'point_of_sale.assets_prod': [
            'pos_lebanon_custom/static/src/app/**/*',
        ],
    },
    'installable': True,
    'license': 'LGPL-3',
}