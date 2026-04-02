# -*- coding: utf-8 -*-
from odoo import models, fields, api
from odoo.exceptions import ValidationError


class ResCompany(models.Model):
    _inherit = 'res.company'
    _description = 'Company Information'

    vat_sapps = fields.Char(string="Tax ID", tracking=True)
    vat = fields.Char(related='vat_sapps', string="Tax ID", tracking=True)
    pos_num_acc = fields.Char(string='Pos Number', tracking=True)
    classification = fields.Selection([
        ('1', '1 Star'),
        ('2', '2 Stars'),
        ('3', '3 Stars'),
        ('4', '4 Stars'),
        ('5', '5 Stars')
    ], string='Classification', help="Classification of the company based on stars.", tracking=True)
    financial_approval_number = fields.Char(
        string='Financial Approval Number',
        help="Unique number provided for financial approval.", tracking=True
    )
    financial_approval_date = fields.Date(
        string='Financial Approval Date',
        help="Date when the financial approval was granted.", tracking=True
    )

    # def write(self, vals):
    #     protected_fields = ['vat_sapps', 'pos_num_acc', 'classification', 'financial_approval_number', 'financial_approval_date']
    #     for field in protected_fields:
    #         if field in vals:
    #             field_label = self._fields[field].string
    #             raise ValidationError(f"You cannot modify the field '{field_label}'!")
    #     return super(ResCompany, self).write(vals)