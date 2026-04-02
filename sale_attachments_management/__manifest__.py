{
    'name': 'Sales Attachments Management',
    'version': '1.0.0',
    'summary': 'Manage and enhance attachments for Sales Orders',
    'description': """
Sales Attachments Management
============================

This module provides:
- Custom list and kanban views for attachments
- Link attachments with Sale Orders
- Filter and search by customer and order
- Group by customer and order
    """,
    'author': 'Mohammad haitham Salman',
    'website': '',
    'category': 'Sales',
    'license': 'LGPL-3',
    'depends': [
        'base',
        'sale',
    ],
    'data': [
        'views/ir_attachment_views.xml',
    ],
    'installable': True,
    'application': True,
}
