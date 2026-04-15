# -*- coding: utf-8 -*-
{
    'name': 'Sales Rep Onboarding & Setup Wizard',
    'version': '18.0.1.0.0',
    'category': 'Sales/Sales',
    'summary': 'Automated Onboarding Wizard for Creating Sales Representatives with Portal Access, Financial Accounts, and Cash Journals.',
    'description': """
Sales Representative Onboarding & Setup Wizard
==============================================
This module provides an advanced, fully automated staging interface (Onboarding Form) to streamline the process of creating a new Sales Representative in Odoo.

Key Features:
-------------
* **One-Click Creation:** Automatically generates a Portal User, Contact Profile, and Sales Rep Profile from minimal input.
* **Smart Data Extraction:** Automatically fetches branch State, default Warehouse, and generates the Branch Code.
* **Logistics Setup:** Auto-creates specific Inventory Locations (e.g., CARS location for CashVan) and assigns proper Operation Types.
* **Financial Automation:** Auto-generates exact sequence-based Cash Accounts (131xx) and multiple Cash Journals (SYP, SPO, USD) linked to the representative.
* **Security & Usability:** Enforces strict validation, sequence generation, and hides sensitive creation steps from non-managers.

Developed by: Mohammad Haitham Salman (SAPPS Group)
    """,
    'author': 'Mohammad Haitham Salman From SAPPS Group',
    'company': 'SAPPS Group',
    'website': 'https://www.s-apps.io/',
    'license': 'OPL-1',
    'depends': [
        'base',
        'mail',
        'account',
        'stock',
        'portal',
        'sales_rep_manager'
    ],
    'data': [
        'security/ir.model.access.csv',
        'views/sales_rep_setup_views.xml',
    ],
    'demo': [],
    'installable': True,
    'application': False,
    'auto_install': False,
}