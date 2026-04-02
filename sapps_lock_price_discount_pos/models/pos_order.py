# -*- coding: utf-8 -*-
from odoo import models, fields


class PosOrder(models.Model):
    _inherit = 'pos.order'

    discount_reason = fields.Char(string='Global Discount Reason', readonly=1)
    source_table = fields.Char(string='Source table', readonly=1)
    is_transfer = fields.Boolean(string='Is Transfer', readonly=1)
    average_guests = fields.Float(string='Average Guests', store=True, compute='compute_average_guests')
    average_orders = fields.Float(string='Average Orders', store=True, compute='compute_average_guests')

    def compute_average_guests(self):
        for record in self:
            total_guests = 0.0
            total_orders = self.env['pos.order'].search_count([])
            pos_orders = self.env['pos.order'].search([('customer_count', '>', 0)])

            for order in pos_orders:
                total_guests += order.customer_count
            # Count total number of orders
            record.average_guests = record.amount_total / total_guests
            record.average_orders = record.amount_total / total_orders if total_orders else 0

    def _export_for_ui(self, order):
        fields = super()._export_for_ui(order)
        fields['discount_reason'] = order.discount_reason
        fields['is_transfer'] = order.is_transfer
        fields['source_table'] = order.source_table
        return fields

    def _order_fields(self, ui_order):
        fields = super()._order_fields(ui_order)
        fields['discount_reason'] = ui_order.get('discount_reason', '')
        fields['is_transfer'] = ui_order.get('is_transfer')
        fields['source_table'] = ui_order.get('source_table')
        return fields


class PosOrderLine(models.Model):
    _inherit = 'pos.order.line'

    discount_line_reason = fields.Char(string='Discount Reason', readonly=1)

    # def _order_line_fields(self, line, session_id=None):
    #     result = super()._order_line_fields(line, session_id)
    #     vals = result[2]
    #     vals['combo_child'] = vals['combo_child']
    #
    #     return result

    def _export_for_ui(self, orderline):
        result = super()._export_for_ui(orderline)
        result['discount_line_reason'] = orderline.discount_line_reason
        return result
