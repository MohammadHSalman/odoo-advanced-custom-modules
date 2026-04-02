from odoo import models, fields, api, _


class FuelVehicle(models.Model):
    """MHAZAS"""
    _name = "fuel.vehicle"

    fuel_id = fields.Many2one('vehicle.contract', string="Fleet Fuel")
    date = fields.Date(default=fields.Date.context_today)
    vehicle_id = fields.Many2one('fleet.vehicle', 'Vehicle', required=True)
    # driver_id = fields.Many2one(related="vehicle_id.driver_id", string="Driver", readonly=False)
    in_value = fields.Float('IN', group_operator="max", related="fuel_id.check_in_fuel")
    out_value = fields.Float('OUT', group_operator="max", related="fuel_id.last_fuel")
    remaining_fuel = fields.Float('Remaining Fuel', compute='compute_remaining_fuel')

    @api.depends('in_value', 'fuel_id')
    def compute_remaining_fuel(self):
        for record in self:
            if record.fuel_id.fuel_ids:
                record.remaining_fuel = (record.fuel_id.last_fuel + record.fuel_id.allowed_fuel_all) - record.in_value
