from odoo import fields, models


class LoyaltyProgram(models.Model):
    _inherit = 'loyalty.program'

    sales_channel_ids = fields.Many2many(
        'res.partner.industry',
        'loyalty_industry_rel',  # جدول الربط الجديد
        'program_id',
        'industry_id',
        string='Sales Channels',
        help='Allowed sales channels for this loyalty program'
    )