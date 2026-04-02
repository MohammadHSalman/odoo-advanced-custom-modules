from odoo import models, fields, api, _


class OdometerVehicle(models.Model):
    """MHAZAS"""
    _name = "odometer.vehicle"

    odometer_id = fields.Many2one('vehicle.contract', string="Fleet Fuel")
    date = fields.Date(default=fields.Date.context_today)
    vehicle_id = fields.Many2one('fleet.vehicle', 'Vehicle', required=True)
    # driver_id = fields.Many2one(related="vehicle_id.driver_id", string="Driver", readonly=False)
    in_value = fields.Float('IN', group_operator="max", related="odometer_id.check_in_odometer")
    out_value = fields.Float('OUT', group_operator="max", related="odometer_id.last_odometer")
    remaining_km = fields.Float('Remaining KM', compute='compute_remaining_km')

    @api.depends('in_value', 'odometer_id')
    def compute_remaining_km(self):
        for record in self:
            if record.odometer_id.odometer_ids:
                record.remaining_km = record.odometer_id.last_odometer + record.odometer_id.allowed_km_all - record.in_value
            # else:
            #     record.remaining_km = 0.0