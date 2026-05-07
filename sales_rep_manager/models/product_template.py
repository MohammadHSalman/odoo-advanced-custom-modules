# -*- coding: utf-8 -*-
from odoo import api, fields, models
from odoo.exceptions import ValidationError


class ProductCategory(models.Model):
    _inherit = 'product.category'
    msl_flag = fields.Boolean(string="MSL (Must Selling)", index=True, default=False)

class ProductTemplate(models.Model):
    _inherit = 'product.template'

    consumer_price = fields.Monetary(
        string="Consumer Price",
        help="Final price the consumer sees in the mobile app.",
        currency_field='currency_id'
    )
    msl_flag = fields.Boolean(string="MSL (Must Selling)", index=True, default=False)
    sales_channel_ids = fields.Many2many(
        'res.partner.industry',
        'product_industry_rel',
        'product_id',
        'industry_id',
        string='Sales Channels',
        help='Allowed sales channels for this product'
    )
    @api.constrains('name')
    def _check_unique_name(self):
        for record in self:
            if record.name:
                domain = [
                    ('name', '=ilike', record.name),
                    ('id', '!=', record.id)
                ]
                existing_product = self.search(domain, limit=1)

                if existing_product:
                    raise ValidationError(f"اسم المنتج '{record.name}' موجود مسبقاً! يرجى اختيار اسم فريد.")



class ProductProduct(models.Model):
    _inherit = 'product.product'

    # نربط حقل المنتج المتغيّر بقيمة التيمبلِت
    consumer_price = fields.Monetary(
        string="Consumer Price",
        related='product_tmpl_id.consumer_price',
        store=True,
        readonly=False
    )
    msl_flag = fields.Boolean(related='product_tmpl_id.msl_flag', store=True, readonly=True)
    sales_channel_ids = fields.Many2many(
        related='product_tmpl_id.sales_channel_ids',
        string='Sales Channels',
        readonly=False
    )