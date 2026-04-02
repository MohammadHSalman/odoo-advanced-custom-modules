from odoo import models, fields


class StockMove(models.Model):
    _inherit = 'stock.move'

    brand_id = fields.Many2one(
        'product.brand',
        related='product_id.categ_id.brand_id',
        store=True
    )

class StockQuant(models.Model):
    _inherit = "stock.quant"

    brand_id = fields.Many2one(
        "product.brand",
        related="product_id.categ_id.brand_id",
        store=True,
        index=True,
        string="Brand"
    )
