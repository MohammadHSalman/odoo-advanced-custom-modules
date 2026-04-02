from odoo import fields, models, api, _
from odoo.exceptions import ValidationError


class FleetVehicle(models.Model):
    """MHAZAS"""
    _inherit = 'fleet.vehicle'

    odometer = fields.Float(
        string='Odometer Value',
        help='Odometer measure of the vehicle at the moment of this log')
    car_category_ids = fields.Many2one(comodel_name='fuel.mang', string='Car Category', required=False)
    manufacturer_year = fields.Char(string="Manufacturer Year")
    engine_cc = fields.Char(string="Engine CC")
    engine_no = fields.Char(string="Engine No")
    stock_no = fields.Char(string="Stock No")
    mulkiya_expiration_date = fields.Date(string="Mulkiya Expiration Date")
    insurance_contract_no = fields.Char(string="Insurance Contract #")
    insurance_type = fields.Selection([
        ('comprehensive', _('تأمين شامل (Comprehensive)')),
        ('comprehensive_oman_uae', _('تأمين شامل عمان / الإمارات (Comprehensive Oman/UAE)')),
        ('third_party', _('طرف ثالث (Third Party)')),
        ('third_party_oman_uae', _('طرف ثالث عمان / الإمارات (Third Party Oman/UAE)')),
    ], string=_('Insurance Type'))
    insurance_start_date = fields.Date(string="Insurance Start Date")
    insurance_expiry_date = fields.Date(string="Insurance Expiry Date")
    regis_date = fields.Date(string="Regis Date")
    insurance_value = fields.Float(string="Insurance Value")
    cylinder = fields.Integer(string='Cylinder')
    # branch = fields.Char(string='Branch')
    branch = fields.Many2many('res.company', string='Branch', index=True)
    # branch = fields.One2many('res.company', 'parent_id', string='Branches')

    last_fuel = fields.Float(string="Last Fuel", copy=False)
    category_id = fields.Many2one('fleet.vehicle.model.category', 'Category', compute='_compute_model_fields',required=True, store=True, readonly=False)

    license_plate = fields.Char(tracking=True, required=True,
                                help='License plate number of the vehicle (i = plate number for a car)')

    _sql_constraints = [
        ('unique_license_plate', 'unique(license_plate)', 'The license plate number must be unique.')
    ]

    @api.constrains('license_plate')
    def _check_license_plate_unique(self):
        for record in self:
            if self.search([('license_plate', '=', record.license_plate), ('id', '!=', record.id)]):
                raise ValidationError('The license plate number must be unique.')

    @api.constrains('last_fuel')
    def _check_fuel_range(self):
        for record in self:
            if record.last_fuel < 0 or record.last_fuel > 8:
                raise ValidationError("Last Fuel must be between 0 and 8")

    @api.model
    def create(self, vals):
        if vals.get('category_id'):
            car_category = self.env['fuel.mang'].search([('car_category_ids', '=', vals['category_id'])], limit=1)
            if car_category:
                vals['car_category_ids'] = car_category.id
            else:
                new_car_category = self.env['fuel.mang'].create({
                    'car_category_ids': vals['category_id'],
                    'full_fuel': 0,  # Set appropriate default values here
                    'selection': 8
                })
                vals['car_category_ids'] = new_car_category.id
        return super(FleetVehicle, self).create(vals)

    @api.model
    def write(self, vals):
        if 'category_id' in vals:
            car_category = self.env['fuel.mang'].search([('car_category_ids', '=', vals['category_id'])], limit=1)
            if car_category:
                vals['car_category_ids'] = car_category.id
            else:
                new_car_category = self.env['fuel.mang'].create({
                    'car_category_ids': vals['category_id'],
                    'full_fuel': 0,  # Set appropriate default values here
                    'selection': 8
                })
                vals['car_category_ids'] = new_car_category.id
        return super(FleetVehicle, self).write(vals)
