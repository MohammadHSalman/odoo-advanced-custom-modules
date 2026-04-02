from odoo import models, fields, api
from odoo.exceptions import ValidationError


class CarReplacementWizard(models.TransientModel):
    """MHAZAS"""
    _name = 'car.replacement.wizard'

    contract_id = fields.Many2one('vehicle.contract', string="Fleet Fuel", compute='compute_contract_id')
    vehicle_id = fields.Many2one('fleet.vehicle', string="Vehicle", related='contract_id.vehicle_id', copy=False)
    check_in_odometer = fields.Float(string='Check IN KM', required=True)
    check_in_fuel = fields.Float(string='Check IN Fuel', required=True)
    new_vehicle_id = fields.Many2one('fleet.vehicle', string="New Vehicle",
                                     domain="[('status', '=', 'available')]", copy=False)
    check_out_odometer = fields.Float(string='Check OUT KM', required=True)
    check_out_fuel = fields.Float(string='Check OUT Fuel', required=True)
    section_number = fields.Char(string='Section Number')
    section_number_new = fields.Char(string='Section Number')

    @api.depends('check_in_odometer')
    def compute_contract_id(self):
        for record in self:
            active_contract_id = self._context.get('active_id')
            record.contract_id = active_contract_id

    def action_apply(self):
        pass
