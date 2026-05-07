from odoo import api, fields, models

class CashVanInvoiceLog(models.Model):
    _name = "cashvan.invoice.log"
    _description = "CashVan Invoice Failed Logs"
    _rec_name = "mobile_invoice_number"

    user_id = fields.Many2one('res.users', string="Sales Representative", required=True)
    partner_id = fields.Many2one('res.partner', string="Customer")
    mobile_invoice_number = fields.Char(string="Mobile Invoice Number")
    error_message = fields.Text(string="Error Message", required=True)
    error_stage = fields.Selection([
        ('duplicate_check', 'Duplicate Check'),
        ('validation', 'Validation'),
        ('sale_order', 'Sale Order Creation'),
        ('picking', 'Delivery Processing'),
        ('invoice', 'Invoice Creation'),
        ('payment', 'Payment Registration'),
        ('other', 'Other'),
    ], default='other', string="Error Stage")
    payload = fields.Text(string="Request Payload (JSON)")  # لتخزين البيانات القادمة
    create_date = fields.Datetime(string="Created At", default=fields.Datetime.now)