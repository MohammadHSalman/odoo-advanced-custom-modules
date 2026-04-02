{
    'name': 'Product Brand Management',
    'version': '18.0',
    'depends': [
        'product',
        'sale',
        'stock'
    ],
    'data': [
        'security/ir.model.access.csv',
        'views/product_brand_views.xml',
        'views/product_category_views.xml',
        'views/sale_report_views.xml',
        'views/product_views.xml',
    ],
    'installable': True,
}