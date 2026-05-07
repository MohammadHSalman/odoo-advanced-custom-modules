from odoo import fields, models, api


class ResCurrency(models.Model):
    _inherit = 'res.currency'
    _description = ''

    is_use = fields.Boolean(
        string='Is Use',
        required=False)
