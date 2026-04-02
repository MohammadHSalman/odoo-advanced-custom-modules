from odoo import fields, models, api


class ResUsers(models.Model):
    """The inherited class ResUsers to add new fields to 'res.users' """
    _inherit = "res.users"

    disable_cancellation = fields.Boolean(
        string="Disable Cancel Order",
        help="Disable the Cancel Order on the POS")
