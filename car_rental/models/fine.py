from odoo import models, api, fields, _
from odoo.exceptions import ValidationError


class FineCar(models.Model):
    """MHAZAS"""
    _name = 'fine.car'
    _rec_name = "serial_number"

    serial_number = fields.Integer(string='Sr', readonly=True)
    receipt_number = fields.Integer(string='Receipt Number', readonly=True)
    agreement_no = fields.Integer(string='Agreement No')
    date_time = fields.Datetime(string='Date & Time', readonly=True)
    payment_date = fields.Date(string='Payment Date', readonly=True)
    transfer_date = fields.Date(string='Transfer Date')
    tor_number = fields.Char(string='TOR Number', readonly=True)
    plate_number = fields.Char(string='Plate Number', readonly=True)
    location = fields.Char(string='Location', readonly=True)
    description = fields.Char(string='Description', readonly=True)
    offender_name = fields.Char(string='Offender Name', readonly=True)
    status = fields.Char(string='Status', readonly=True)
    customer_name = fields.Char(string='Custmer name ')
    amount = fields.Float(string='Amount (OMR)', readonly=True)
    paid_or_not_paid = fields.Selection(selection=[
        ('yse', 'Paid'),
        ('no', 'Not Paid')
    ], string='Paid or not Paid')
    transfer_customer = fields.Many2one('res.partner', string='Transfer to Customer name or no ')
