from odoo import fields, models


class CashVanInvoiceLog(models.Model):
    _name = "cashvan.invoice.log"
    _description = "CashVan Invoice Failed Logs"
    _rec_name = "mobile_invoice_number"

    user_id = fields.Many2one('res.users', string="Sales Representative", required=True)
    partner_id = fields.Many2one('res.partner', string="Customer")
    mobile_invoice_number = fields.Char(string="Mobile Invoice Number")
    error_message = fields.Text(string="Error Message", required=True)
    error_stage = fields.Selection([
        ('validation', 'Validation'),
        ('duplicate_check', 'Duplicate Check'),
        ('picking_preparation', 'Picking Preparation'),
        ('picking', 'Picking Creation'),
        ('picking_validation', 'Picking Validation'),
        ('credit_note_create', 'Credit Note Creation'),
        ('payment', 'Payment'),
        ('other', 'Other'),
    ], string='Error Stage', required=True, default='other')
    payload = fields.Text(string="Request Payload (JSON)")
    create_date = fields.Datetime(string="Created At", default=fields.Datetime.now)
