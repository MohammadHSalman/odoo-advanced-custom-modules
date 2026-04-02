# -*- coding: utf-8 -*-
from odoo import models, fields


class PosOrder(models.Model):
    _inherit = 'pos.order'

    discount_reason = fields.Char(string='Global Discount Reason', readonly=1)

    def _export_for_ui(self, order):
        fields = super()._export_for_ui(order)
        fields['discount_reason'] = order.discount_reason

        return fields

    def _order_fields(self, ui_order):
        fields = super()._order_fields(ui_order)
        fields['discount_reason'] = ui_order.get('discount_reason', '')

        return fields


class PosOrderLine(models.Model):
    _inherit = 'pos.order.line'

    discount_line_reason = fields.Char(string='Discount Reason', readonly=1)

    def _export_for_ui(self, orderline):
        result = super()._export_for_ui(orderline)
        result['discount_line_reason'] = orderline.discount_line_reason
        return result
