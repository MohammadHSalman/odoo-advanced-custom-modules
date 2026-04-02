from odoo import models, fields


class ResUsers(models.Model):
    _inherit = 'res.users'

    is_super_admin = fields.Boolean(
        string='Is Admin',
        required=False)
