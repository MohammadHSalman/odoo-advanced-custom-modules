from odoo import fields, models


class ResCompany(models.Model):
    """MHAZAS"""
    _inherit = 'res.company'

    minimum_age = fields.Integer(string='Minimum age in the contract', required=True, default="18")
    maximum_age = fields.Integer(string='Maximum age in the contract', required=True, default="75")
    passport_deadline = fields.Integer(string='Passport deadline', required=True, default="1")
    driving_certificate_deadline = fields.Integer(string='Driving certificate deadline', required=True, default="1")
