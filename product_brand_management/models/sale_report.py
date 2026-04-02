from odoo import models, fields


class SaleReport(models.Model):
    _inherit = 'sale.report'

    brand_id = fields.Many2one(
        'product.brand',
        string="Brand",
        readonly=True
    )

    brand_count = fields.Integer(
        string="Brand Count",
        readonly=True,
        aggregator="count_distinct"
    )

    def _select_additional_fields(self):
        res = super()._select_additional_fields()

        res['brand_id'] = "pc.brand_id"
        res['brand_count'] = "pc.brand_id"  # نفس المصدر ولكن الحقل في الاعلى integer ليتم العد

        return res

    def _from_sale(self):
        res = super()._from_sale()
        res += """
            LEFT JOIN product_category pc ON t.categ_id = pc.id
        """
        return res

    def _group_by_sale(self):
        res = super()._group_by_sale()
        res += ", pc.brand_id"
        return res