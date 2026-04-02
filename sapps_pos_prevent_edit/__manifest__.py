{
    'name': 'Sapps POS Prevent Edit',
    'summary': 'Enhance control over orders in POS by preventing modification or cancellation of sent orders.',
    'description': """
        This module provides advanced tools to ensure the integrity of order management in the Point of Sale system. 
        It prevents employees from modifying or canceling items in orders that have already been sent to the kitchen, 
        unless approved by a manager. This enhances accuracy and accountability within the workplace.

        **Key Features:**
        - Lock sent orders to prevent unauthorized modifications.
        - Require manager approval for sensitive actions like item removal or order cancellation.
        - Integration with the access management system for precise role-based permissions.
        - Flexible discount management with an improved user interface.
        - User-friendly design that ensures smooth adaptation to the new restrictions.
    """,
    'author': 'Mohammad Haitham Salman',
    'category': 'Point of Sale',
    'version': '17.0',
    'depends': ['base', 'point_of_sale', 'simplify_access_management', 'simplify_pos_access_management'],
    'data': [
        'views/res_users_views.xml',
        'views/pos_order_views.xml',
    ],
    'assets': {
        'point_of_sale._assets_pos': [
            'sapps_pos_prevent_edit/static/src/js/pos_store.js',
            'sapps_pos_prevent_edit/static/src/js/pos_order.js',
            'sapps_pos_prevent_edit/static/src/js/product_screen.js',
            'sapps_pos_prevent_edit/static/src/js/discount_button.js',
            'sapps_pos_prevent_edit/static/src/js/global_discount_popup.js',
            'sapps_pos_prevent_edit/static/src/js/models.js',
            'sapps_pos_prevent_edit/static/src/js/global_discount_popup.xml',
        ],
    },
    'installable': True,
    'application': False,
}
