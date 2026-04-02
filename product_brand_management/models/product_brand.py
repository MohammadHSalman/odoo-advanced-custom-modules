from odoo import models, fields


class ProductBrand(models.Model):
    _name = 'product.brand'
    _description = 'Product Brand'

    name = fields.Char(string="Brand Name", required=True)
    active = fields.Boolean(default=True)
    note = fields.Text()