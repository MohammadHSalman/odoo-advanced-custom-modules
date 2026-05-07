# -*- coding: utf-8 -*-
from odoo import fields, models


class ResPartner(models.Model):
    _inherit = "res.partner"

    customer_classification = fields.Selection(
        selection=[
            ("A", "A"),
            ("B", "B"),
            ("C", "C"),
        ],
        string="Customer Classification",
        help="Optional classification tier for the customer.",
        tracking=True,
        index=True,
        required=False,
        default=False,
    )
    