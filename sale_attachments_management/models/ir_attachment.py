from odoo import models, fields, api


class IrAttachment(models.Model):
    _inherit = 'ir.attachment'

    sale_order_partner_id = fields.Many2one(
        'res.partner',
        string='Customer',
        compute='_compute_sale_order_partner',
        store=True
    )

    sale_order_id = fields.Many2one(
        'sale.order',
        string='Order',
        compute='_compute_sale_order',
        store=True
    )

    @api.depends('res_model', 'res_id')
    def _compute_sale_order(self):
        for rec in self:
            if rec.res_model == 'sale.order':
                rec.sale_order_id = rec.res_id
            else:
                rec.sale_order_id = False

    @api.depends('res_model', 'res_id')
    def _compute_sale_order_partner(self):
        for rec in self:
            rec.sale_order_partner_id = False
            if rec.res_model == 'sale.order' and rec.res_id:
                order = self.env['sale.order'].browse(rec.res_id)
                rec.sale_order_partner_id = order.partner_id
