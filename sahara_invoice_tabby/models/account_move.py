# -*- coding: utf-8 -*-

from odoo import models, fields, api


class AccountMove(models.Model):
    _inherit = 'account.move'
    _description = 'AccountMove'

    tabby_percentage = fields.Float(string='Tabby Percentage')
