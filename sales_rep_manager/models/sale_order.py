from odoo import models, fields, api

from odoo.exceptions import ValidationError


class SaleOrderMSLLine(models.Model):
    _name = 'sale.order.msl.line'
    _description = 'MSL result per order line (product/category)'

    order_id = fields.Many2one('sale.order', required=True, index=True, ondelete='cascade')
    product_id = fields.Many2one('product.product', index=True)
    categ_id = fields.Many2one('product.category', index=True)
    status = fields.Selection([('available', 'متوفر'), ('unavailable', 'غير متوفر')],
                              default='unavailable', required=True)
    note = fields.Char()

    @api.constrains('product_id', 'categ_id')
    def _check_target(self):
        for rec in self:
            if not rec.product_id and not rec.categ_id:
                raise ValidationError("MSL line must have product_id or categ_id.")


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    user_id = fields.Many2one(
        comodel_name='res.users',
        string="Salesperson",
        compute='_compute_user_id',
        store=True, readonly=False, precompute=True, index=True,
        tracking=2, domain=[]
    )
    msl_result_ids = fields.One2many('sale.order.msl.line', 'order_id', string="MSL Results")
    client_order_ref = fields.Char(index=True)


class SaleReport(models.Model):
    _inherit = 'sale.report'

    customer_count = fields.Integer(
        string="Customer Count",
        readonly=True,
        aggregator="count_distinct"
    )
    order_count = fields.Integer(
        string="Order Count",
        readonly=True,
        # هذا هو السر: يقوم بعد القيم الفريدة فقط
        # فلو تكرر رقم الفاتورة 5 مرات (بسبب وجود 5 منتجات)، سيحسبها مرة واحدة
        aggregator="count_distinct"
    )

    def _select_additional_fields(self):
        res = super()._select_additional_fields()

        # عدد الزبائن
        res['customer_count'] = "s.partner_id"

        # عدد الطلبات (Sale Order ID)
        res['order_count'] = "s.id"

        return res