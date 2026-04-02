# -*- coding: utf-8 -*-

{
    'name': 'Lock Price & Discount Pos',
    'version': '17.0',
    'category': 'Point of Sale',
    'sequence': 6,
    'author': 'Mohammad Haitham Salman',
    'summary': 'Allows to lock Price and discount button in POS and set Reason for open it.',
    'description': "Allows to lock Price and discount button in POS and set Reason for open it.",
    'depends': ['point_of_sale', 'pos_access_right_user', 'pos_restaurant'],
    'data': [
        "views/pos_order_views.xml",
        "views/pos_order_report.xml",
    ],
    'assets': {
        'point_of_sale._assets_pos': [
            # js
            'sapps_lock_price_discount_pos/static/src/js/product_screen.js',
            'sapps_lock_price_discount_pos/static/src/js/pos_order.js',
            'sapps_lock_price_discount_pos/static/src/js/global_discount_popup.js',
            'sapps_lock_price_discount_pos/static/src/js/models.js',
            'sapps_lock_price_discount_pos/static/src/js/discount_button.js',
            # 'sapps_lock_price_discount_pos/static/src/js/number_buffer_service.js',
            'sapps_lock_price_discount_pos/static/src/js/pos_store.js',
            # xml
            'sapps_lock_price_discount_pos/static/src/xml/global_discount_popup.xml',

        ],
    },

    'installable': True,
    'website': '',
    'auto_install': False,
}
