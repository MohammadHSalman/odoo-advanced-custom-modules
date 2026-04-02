from odoo import models, fields


class ProductCategory(models.Model):
    _inherit = 'product.category'

    brand_id = fields.Many2one(
        'product.brand',
        string="Brand"
    )


class ProductTemplate(models.Model):
    _inherit = "product.template"

    brand_id = fields.Many2one(
        "product.brand",
        related="categ_id.brand_id",
        store=True,
        index=True,
        string="Brand"
    )


class ProductProduct(models.Model):
    _inherit = "product.product"

    brand_id = fields.Many2one(
        "product.brand",
        related="categ_id.brand_id",
        store=True,
        index=True,
        string="Brand"
    )
