from odoo import models, fields, api
from odoo.exceptions import ValidationError


class RouteLine(models.Model):
    _name = 'route.line'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _description = 'Route Line'
    _rec_name = 'route_name'

    route_number = fields.Char(string="Route Number", required=True,tracking=True)
    route_name = fields.Char(string="Route Name", required=True,tracking=True)

    country_id = fields.Many2one(
        'res.country',
        string="Country",
        required=True,tracking=True,
        default=lambda self: self.env.ref('base.sy').id
    )
    governorate_id = fields.Many2one(
        'res.country.state',
        string="Governorate",
        required=True,tracking=True,
        domain="[('country_id', '=', country_id)]"
    )
    # ملاحظة: هذا الحقل يشير إلى المدن (res.city)
    area_ids = fields.Many2many(
        'res.city',
        string="Areas",tracking=True,
        domain="[('state_id', '=', governorate_id)]"
        # تم إزالة required=True ليتمكن المستخدم من تركها فارغة لجلب كل المحافظة
    )

    sales_channel_ids = fields.Many2many('res.partner.industry', string="Sales Channels",tracking=True)

    # أعدنا compute ليعمل بشكل آلي
    partner_ids = fields.Many2many(
        'res.partner',
        string="Customers",
        store=True,
        readonly=False,
        tracking=True
    )
    company_id = fields.Many2one(
        'res.company',
        string='Company',
        required=True,
        default=lambda self: self.env.company,
        readonly=True,
    )

    @api.onchange('governorate_id')
    def _onchange_governorate_id(self):
        for rec in self:
            rec.area_ids = [(5, 0, 0)]
            rec.partner_ids = [(5, 0, 0)]

            if rec.governorate_id:
                return {
                    'domain': {
                        'partner_ids': [
                            ('company_id', '=', rec.company_id.id),
                            ('customer_rank', '>', 0),
                        ],
                        'area_ids': [
                            ('state_id', '=', rec.governorate_id.id),
                        ],
                    }
                }
