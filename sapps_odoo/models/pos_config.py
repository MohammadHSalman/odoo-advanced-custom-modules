from odoo import fields, models


class PosConfig(models.Model):
    _inherit = 'pos.config'

    pos_num = fields.Char(string='Pos Number', store=True, readonly=True, tracking=True)
