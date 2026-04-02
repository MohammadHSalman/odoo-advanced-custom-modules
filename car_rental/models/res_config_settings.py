# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    """MHAZAS"""
    _inherit = ['res.config.settings']

    minimum_age = fields.Integer(string='Minimum age in the contract', required=True, related='company_id.minimum_age')
    maximum_age = fields.Integer(string='Maximum age in the contract', required=True, related='company_id.maximum_age')
    passport_deadline = fields.Integer(string='Passport deadline', required=True, related='company_id.passport_deadline')
    driving_certificate_deadline = fields.Integer(string='Driving certificate deadline', required=True, related='company_id.driving_certificate_deadline')
