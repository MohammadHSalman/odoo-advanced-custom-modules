from odoo import models, fields, api
from odoo.exceptions import ValidationError


class VehicleContractWizard(models.TransientModel):
    """MHAZAS"""
    _name = 'vehicle.contract.wizard'

    contract_id = fields.Many2one('vehicle.contract', string="Fleet Fuel", compute='compute_contract_id')
    check_in_odometer = fields.Float(string='Check IN KM', required=True)
    check_out_odometer = fields.Float(string='Check OUT KM', required=True, related='contract_id.last_odometer')
    extra_odometer = fields.Float(string='Extra KM', required=True)

    check_in_fuel = fields.Float(string='Check IN Fuel', required=True)
    check_out_fuel = fields.Float(string='Check OUT Fuel', required=True, related='contract_id.last_fuel')
    extra_fuel = fields.Float(string='Extra Fuel', required=True)

    date_of_check_in = fields.Datetime(string='Date Of Check In', required=True, index=True, copy=False,
                                       default=fields.Datetime.now)
    extra_days = fields.Float(string="Extra days")

    @api.onchange('check_in_odometer')
    def compute_extra(self):
        for rec in self:
            extra_o = (rec.contract_id.allowed_km_all + rec.check_out_odometer)
            if extra_o < rec.check_in_odometer:
                rec.extra_odometer = rec.check_in_odometer - extra_o
            else:
                rec.extra_odometer = 0.0

    @api.onchange('check_in_fuel')
    def compute_extra_fuel(self):
        for rec in self:

            extra_f = (rec.check_out_fuel - rec.contract_id.allowed_fuel_all)
            if extra_f > rec.check_in_fuel > 0.0:
                rec.extra_fuel = extra_f - rec.check_in_fuel
            else:
                rec.extra_fuel = 0.0

    @api.onchange('check_in_odometer')
    def update_in_value(self):
        for record in self:
            record.contract_id.odometer_ids.in_value = record.check_in_odometer

    @api.onchange('check_in_fuel')
    def update_in_value_fuel(self):
        for record in self:
            record.contract_id.fuel_ids.in_value = record.check_in_fuel

    @api.depends('check_in_odometer')
    def compute_contract_id(self):
        for record in self:
            active_contract_id = self._context.get('active_id')
            record.contract_id = active_contract_id

    def action_apply(self):
        contracts = self.env['vehicle.contract'].browse(self._context.get('active_ids'))
        extra_service_obj = self.env['extra.service']
        product_extra_km = self.env['product.product'].search([('name', '=', 'Extra KM')], limit=1)
        product_extra_fuel = self.env['product.product'].search([('name', '=', 'Extra Fuel')], limit=1)
        product_extra_days = self.env['product.product'].search([('name', '=', 'Extra Days')], limit=1)

        for contract in contracts:
            contract.status = 'c_return'
            contract.check_in_odometer = self.check_in_odometer
            contract.vehicle_id.odometer = self.check_in_odometer
            contract.check_in_fuel = self.check_in_fuel
            contract.vehicle_id.last_fuel = self.check_in_fuel
            if self.extra_odometer > 0.0:
                amount = contract.vehicle_id.extra_charge_km
                extra_service = extra_service_obj.create({
                    'product_id': product_extra_km.id,
                    'product_qty': self.extra_odometer,
                    'description': 'Extra KM',
                    'amount': amount,

                })

                contract.write({'extra_service_ids': [(4, extra_service.id)]})
            if self.extra_days > 0.0:
                amount = contract.vehicle_id.rent_day
                extra_service = extra_service_obj.create({
                    'product_id': product_extra_days.id,
                    'product_qty': self.extra_days,
                    'description': 'Extra Days',
                    'amount': amount,
                })

                contract.write({'extra_service_ids': [(4, extra_service.id)]})
            if self.extra_fuel > 0.0:
                amount = contract.vehicle_id.car_category_ids.amount_per_section
                extra_service = extra_service_obj.create({
                    'product_id': product_extra_fuel.id,
                    'product_qty': self.extra_fuel,
                    'description': 'Extra Fuel',
                    'amount': amount,
                })

                # إضافة السطر إلى extra_service_ids في العقد
                contract.write({'extra_service_ids': [(4, extra_service.id)]})

        return {'type': 'ir.actions.act_window_close'}

    @api.constrains('check_in_fuel', 'check_out_fuel')
    def _check_fuel_range(self):
        for record in self:
            if record.check_in_fuel < 0 or record.check_in_fuel > 8:
                raise ValidationError("Check IN Fuel must be between 0 and 8")
            if record.check_out_fuel < 0 or record.check_out_fuel > 8:
                raise ValidationError("Check OUT Fuel must be between 0 and 8")
