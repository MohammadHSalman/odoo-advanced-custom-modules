# -*- coding: utf-8 -*-
from odoo import api, models, fields


class ReportPosOrder(models.Model):
    _inherit = "report.pos.order"

    margin_percentage = fields.Float(string='Margin Percentage', readonly=True)
    product_cost = fields.Float(string='Product Cost', readonly=True)


    def _select(self):
        sql = super()._select()
        sql += """
                , pt.standard_price AS product_cost
                , CASE
                    WHEN SUM(l.price_subtotal) = 0 THEN 0
                    ELSE SUM(l.price_subtotal - COALESCE(l.total_cost, 0) / CASE COALESCE(s.currency_rate, 0) WHEN 0 THEN 1.0 ELSE s.currency_rate END) 
                          / SUM(l.price_subtotal) * 100
                  END AS margin_percentage
        """
        return sql

    def _group_by(self):
        sql = super()._group_by()
        sql += " , pt.standard_price"
        return sql


