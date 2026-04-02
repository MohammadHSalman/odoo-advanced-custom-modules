from odoo import fields, models, api, _
from datetime import datetime, timedelta

from odoo.exceptions import ValidationError


class CarReplacement(models.Model):
    _name = 'car.replacement'
    _description = 'CarReplacement'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _rec_name = 'r_reference_no'

    r_reference_no = fields.Char(string='Reference No', required=True, readonly=True, default=lambda self: _('New'),
                                 copy=False)

    customer_id = fields.Many2one("res.partner", required=True)
    contract_id = fields.Many2one("vehicle.contract", required=True)
    customer_phone = fields.Char(string="Phone")
    customer_email = fields.Char(string="Email")
    customer_mobile = fields.Char(string="Mobile")

    date_of_replacement = fields.Datetime(string='Date Of Replacement', required=True, index=True, copy=False,
                                          default=fields.Datetime.now)

    vehicle_id = fields.Many2one('fleet.vehicle', string="Vehicle",related='contract_id.vehicle_id')

    model_year = fields.Char(string="Model", copy=False)

    fuel_type = fields.Selection([('diesel', 'Diesel'),
                                  ('gasoline', 'Gasoline'),
                                  ('full_hybrid', 'Full Hybrid'),
                                  ('plug_in_hybrid_diesel', 'Plug-in Hybrid Diesel'),
                                  ('plug_in_hybrid_gasoline', 'Plug-in Hybrid Gasoline'),
                                  ('cng', 'CNG'),
                                  ('lpg', 'LPG'),
                                  ('hydrogen', 'Hydrogen'),
                                  ('electric', 'Electric')],
                                 string="Fuel Type")
    transmission = fields.Selection([('manual', 'Manual'), ('automatic', 'Automatic')], string="Transmission",
                                    copy=False)
    license_plate = fields.Char(string="License Plate")
    odometer_unit = fields.Selection([('kilometers', 'km'), ('miles', 'mi')], 'Odometer Unit',
                                     default='kilometers', copy=False)
    last_odometer = fields.Float(string="Last Odometer", copy=False)
    driver_id = fields.Many2one('res.partner', string="Driver")
    check_in_odometer = fields.Float(string="Check In Odometer", copy=False)
    last_fuel = fields.Float(string="Last Fuel", copy=False, related='vehicle_id.last_fuel')
    check_in_fuel = fields.Float(string="Check In Fuel", copy=False)

    r_vehicle_id = fields.Many2one('fleet.vehicle', string="Replacement Vehicle",
                                   copy=False)
    r_model_year = fields.Char(string="Model", copy=False)

    r_fuel_type = fields.Selection([('diesel', 'Diesel'),
                                    ('gasoline', 'Gasoline'),
                                    ('full_hybrid', 'Full Hybrid'),
                                    ('plug_in_hybrid_diesel', 'Plug-in Hybrid Diesel'),
                                    ('plug_in_hybrid_gasoline', 'Plug-in Hybrid Gasoline'),
                                    ('cng', 'CNG'),
                                    ('lpg', 'LPG'),
                                    ('hydrogen', 'Hydrogen'),
                                    ('electric', 'Electric')],
                                   string="Fuel Type")
    r_transmission = fields.Selection([('manual', 'Manual'), ('automatic', 'Automatic')], string="Transmission",
                                      copy=False)
    r_license_plate = fields.Char(string="License Plate")
    r_odometer_unit = fields.Selection([('kilometers', 'km'), ('miles', 'mi')], 'Odometer Unit',
                                       default='kilometers', copy=False)
    r_last_odometer = fields.Float(string="Last Odometer", copy=False, related='r_vehicle_id.odometer')
    r_driver_id = fields.Many2one('res.partner', string="Driver")
    r_check_in_odometer = fields.Float(string="Check In Odometer", copy=False)
    r_last_fuel = fields.Float(string="Last Fuel", copy=False, related='r_vehicle_id.last_fuel')
    r_check_in_fuel = fields.Float(string="Check In Fuel", copy=False)

    allowed_km_all = fields.Float(string='Expected KM', copy=False, related='contract_id.allowed_km_all')
    allowed_fuel_all = fields.Float(string='Expected Fuel', copy=False, related='contract_id.allowed_fuel_all')
    show_invoice_button = fields.Boolean(string='Show Invoice Button', compute='_compute_show_invoice_button')
    show_replace_invoice_button = fields.Boolean(string='Show Replace Invoice Button',
                                                 compute='_compute_show_replace_invoice_button')
    contract_ids = fields.Many2many('vehicle.contract', string="Available Contracts", compute='_compute_contract_ids')
    responsible_id = fields.Many2one('res.users', default=lambda self: self.env.user, required=True)
    is_super_admin = fields.Boolean(
        string='Is Admin',
        required=False)

    @api.onchange('responsible_id')
    def onchange_method(self):
        if self.responsible_id.is_super_admin:
            self.is_super_admin = True
        else:
            self.is_super_admin = False

    @api.onchange('vehicle_id')
    def get_vehicle_details(self):
        for rec in self:
            if rec.vehicle_id:
                rec.last_odometer = rec.vehicle_id.odometer

    @api.onchange('last_odometer')
    def set_vehicle_details(self):
        for rec in self:
            if rec.vehicle_id:
                rec.vehicle_id.odometer = rec.last_odometer

    @api.depends('customer_id')
    def _compute_contract_ids(self):
        for record in self:
            if record.customer_id:
                contracts = self.env['vehicle.contract'].search([('customer_id', '=', record.customer_id.id)])
            else:
                contracts = self.env['vehicle.contract'].search([])
            record.contract_ids = contracts

    # @api.depends('contract_id')
    # def _compute_vehicle_id(self):
    #     for rec in self:
    #         if rec.contract_id:
    #             replacement_count = self.env['car.replacement'].search([('contract_id', '=', rec.contract_id.id)],
    #                                                                    order='date_of_replacement desc', limit=1)
    #             if replacement_count:
    #                 rec.vehicle_id = replacement_count.r_vehicle_id
    #             else:
    #                 rec.vehicle_id = rec.contract_id.vehicle_id

    @api.onchange('customer_id')
    def get_r_customer_details(self):
        for rec in self:
            if rec.customer_id:
                rec.customer_phone = rec.customer_id.phone
                rec.customer_mobile = rec.customer_id.mobile
                rec.customer_email = rec.customer_id.email
            else:
                rec.customer_phone = False
                rec.customer_mobile = False
                rec.customer_email = False

    @api.onchange('contract_id')
    def get_contract_details(self):
        for rec in self:
            if rec.contract_id:
                rec.customer_id = rec.contract_id.customer_id.id
                self.get_r_customer_details()  # لتحديث تفاصيل العميل أيضاً
            else:
                rec.customer_id = False

    @api.model
    def create(self, vals):
        if vals.get('contract_id'):
            contract = self.env['vehicle.contract'].browse(vals['contract_id'])
            reference_no = contract.reference_no
            replacement_count = self.search_count([('contract_id', '=', vals['contract_id'])])
            vals['r_reference_no'] = f"R-{reference_no}-{replacement_count + 1}"
        return super(CarReplacement, self).create(vals)

    @api.onchange('r_vehicle_id')
    def get_r_vehicle_details(self):
        for rec in self:
            if rec.r_vehicle_id:
                rec.r_driver_id = rec.r_vehicle_id.driver_id
                rec.r_odometer_unit = rec.r_vehicle_id.odometer_unit
                rec.r_model_year = rec.r_vehicle_id.model_year
                rec.r_transmission = rec.r_vehicle_id.transmission
                rec.r_fuel_type = rec.r_vehicle_id.fuel_type
                rec.r_license_plate = rec.r_vehicle_id.license_plate

    @api.onchange('vehicle_id')
    def get_vehicle_details(self):
        for rec in self:
            if rec.vehicle_id:
                rec.driver_id = rec.vehicle_id.driver_id
                rec.last_odometer = rec.vehicle_id.odometer
                rec.odometer_unit = rec.vehicle_id.odometer_unit
                rec.model_year = rec.vehicle_id.model_year
                rec.transmission = rec.vehicle_id.transmission
                rec.fuel_type = rec.vehicle_id.fuel_type
                rec.license_plate = rec.vehicle_id.license_plate

    @api.depends('check_in_odometer', 'allowed_km_all', 'check_in_fuel', 'allowed_fuel_all')
    def _compute_show_invoice_button(self):
        for record in self:
            record.show_invoice_button = (
                    (record.check_in_odometer > record.allowed_km_all + record.last_odometer) or
                    (record.check_in_fuel and record.check_in_fuel < record.allowed_fuel_all + record.last_fuel)
            )

    def action_create_invoice(self):
        for record in self:
            invoice_lines = []
            if record.check_in_odometer > record.allowed_km_all + record.last_odometer:
                excess_km = record.check_in_odometer - (record.allowed_km_all + record.last_odometer)
                print(record.check_in_odometer,'record.check_in_odometer')
                print(record.allowed_km_all,'record.allowed_km_all')
                print(record.last_odometer,'record.last_odometer')
                print(excess_km,'excess_km')
                amount = record.vehicle_id.extra_charge_km
                invoice_lines.append((0, 0, {
                    'name': 'Excess KM Charge %s' % record.vehicle_id.name,
                    'quantity': excess_km,
                    'price_unit': amount,
                }))
            if record.check_in_fuel < record.allowed_fuel_all + record.last_fuel:
                excess_fuel = record.check_in_fuel - (record.allowed_fuel_all + record.last_fuel)
                amount = record.vehicle_id.car_category_ids.amount_per_section
                invoice_lines.append((0, 0, {
                    'name': 'Excess Fuel Charge %s' % record.vehicle_id.name,
                    'quantity': -1 * excess_fuel,
                    'price_unit': amount,
                }))

            if invoice_lines:
                current_date = datetime.now().date()
                invoice_vals = {
                    'partner_id': record.customer_id.id,
                    'move_type': 'out_invoice',
                    'invoice_date': current_date,
                    'vehicle_contract_id': record.contract_id.id,
                    'invoice_line_ids': invoice_lines,
                    'final': 'replace'
                }
                invoice_id = self.env['account.move'].create(invoice_vals)
                return {
                    'type': 'ir.actions.act_window',
                    'name': _('Invoice'),
                    'res_model': 'account.move',
                    'res_id': invoice_id.id,
                    'view_mode': 'form',
                    'target': 'current'
                }

    @api.depends('check_in_odometer', 'r_check_in_odometer', 'check_in_fuel', 'r_check_in_fuel')
    def _compute_show_replace_invoice_button(self):
        for record in self:
            record.show_replace_invoice_button = (
                    (record.check_in_odometer < record.r_check_in_odometer + record.r_last_odometer) or
                    (record.r_check_in_fuel and record.check_in_fuel > record.r_check_in_fuel + record.r_last_fuel)
            )

    def action_create_replace_invoice(self):
        for record in self:
            invoice_lines = []
            if record.check_in_odometer < record.r_check_in_odometer + record.r_last_odometer:
                excess_km = record.check_in_odometer - record.r_check_in_odometer + record.r_last_odometer
                amount = record.vehicle_id.extra_charge_km
                invoice_lines.append((0, 0, {
                    'name': 'Excess KM Charge %s' % record.r_vehicle_id.name,
                    'quantity': excess_km,
                    'price_unit': amount,
                }))
            if record.check_in_fuel > record.r_check_in_fuel + record.r_last_fuel:
                excess_fuel = record.check_in_fuel - record.r_check_in_fuel + record.r_last_fuel
                amount = record.vehicle_id.car_category_ids.amount_per_section
                invoice_lines.append((0, 0, {
                    'name': 'Excess Fuel Charge %s' % record.r_vehicle_id.name,
                    'quantity': excess_fuel,
                    'price_unit': amount,
                }))

            if invoice_lines:
                current_date = datetime.now().date()
                invoice_vals = {
                    'partner_id': record.customer_id.id,
                    'move_type': 'out_invoice',
                    'invoice_date': current_date,
                    'vehicle_contract_id': record.contract_id.id,
                    'invoice_line_ids': invoice_lines,
                    'final': 'replace'
                }
                invoice_id = self.env['account.move'].create(invoice_vals)
                return {
                    'type': 'ir.actions.act_window',
                    'name': _('Invoice'),
                    'res_model': 'account.move',
                    'res_id': invoice_id.id,
                    'view_mode': 'form',
                    'target': 'current'
                }

    def action_add_new_replacement(self):
        self.ensure_one()
        context = {
            'default_customer_id': self.customer_id.id,
            'default_contract_id': self.contract_id.id,
            'default_date_of_replacement': fields.Datetime.now(),
            'default_vehicle_id': self.r_vehicle_id.id,
            'default_allowed_km_all': self.check_in_odometer - (self.allowed_km_all + self.last_odometer),
            'default_allowed_fuel_all': self.check_in_fuel - (self.allowed_fuel_all + self.last_fuel),
        }
        return {
            'type': 'ir.actions.act_window',
            'name': _('New Car Replacement'),
            'res_model': 'car.replacement',
            'view_mode': 'form',
            'context': context,
            'target': 'current'
        }

    @api.constrains('check_in_fuel')
    def _check_fuel_range(self):
        for record in self:
            if record.check_in_fuel < 0 or record.check_in_fuel > 8:
                raise ValidationError("Check IN Fuel must be between 0 and 8")
            if record.r_check_in_fuel < 0 or record.r_check_in_fuel > 8:
                raise ValidationError("Check IN Fuel must be between 0 and 8")
            if record.last_fuel < 0 or record.last_fuel > 8:
                raise ValidationError("Check IN Fuel must be between 0 and 8")
            if record.r_last_fuel < 0 or record.r_last_fuel > 8:
                raise ValidationError("Check OUT Fuel must be between 0 and 8")
