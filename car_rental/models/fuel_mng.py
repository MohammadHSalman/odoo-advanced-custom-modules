from odoo import models, api, fields, _
from odoo.exceptions import ValidationError


class FuelMang(models.Model):
    """MHAZAS"""
    _name = 'fuel.mang'
    _rec_name = "car_category_ids"

    # car_category_ids = fields.Many2one(comodel_name='car.category', string='Car Category', required=True)
    car_category_ids = fields.Many2one('fleet.vehicle.model.category', 'Category', required=True)
    full_fuel = fields.Integer(string='Full Fuel', required=True, default=1)
    selection = fields.Integer(string='Selection', required=True, default=8)
    amount_per_section = fields.Float(string='Amount Per Section', compute='compute_amount_per_section')
    currency_id = fields.Many2one('res.currency', compute='_compute_currency_id', store=True)

    @api.depends('car_category_ids')
    def _compute_currency_id(self):
        for record in self:
            record.currency_id = record.env.company.currency_id

    @api.depends('full_fuel', 'selection')
    def compute_amount_per_section(self):
        for record in self:
            if record.selection != 0:  # تجنب القسمة على الصفر
                record.amount_per_section = record.full_fuel / record.selection
            else:
                record.amount_per_section = 0.0  # أو أي قيمة تعتبر مناسبة في حالة القسمة على الصفر
