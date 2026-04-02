from odoo import models, fields

class PosOrderAuditLog(models.Model):
    _name = 'pos.order.audit.log'
    _description = 'POS Order Audit Log'

    action = fields.Char(string="Action")
    user_id = fields.Many2one('res.users', string="User")
    pos_order_id = fields.Many2one('pos.order', string="POS Order")
    pos_order_line_id = fields.Many2one('pos.order.line', string="POS Order Line")
    product_id = fields.Many2one('product.product', string="Product")
    quantity = fields.Float(string="Quantity")
    price_unit = fields.Float(string="Unit Price")
    timestamp = fields.Datetime(string="Timestamp")
    receipt_num = fields.Char(string="Receipt Number")
