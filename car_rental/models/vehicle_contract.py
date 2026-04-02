from odoo import models, fields, api, _
from odoo.exceptions import ValidationError
from datetime import datetime, timedelta
from dateutil.relativedelta import relativedelta


class VehicleContract(models.Model):
    """MHAZAS"""
    _inherit = 'vehicle.contract'

    @api.model
    def _get_pick_up_country_domain(self):
        location_car_countries = self.env['location.car'].search([]).mapped('country_id.id')
        return [('id', 'in', location_car_countries)]

    @api.model
    def _get_drop_off_country_domain(self):
        location_car_countries = self.env['location.car'].search([]).mapped('country_id.id')
        return [('id', 'in', location_car_countries)]

    pick_up_country_id = fields.Many2one(
        "res.country",
        domain=_get_pick_up_country_domain,
        string="Pick Up Country"
    )
    drop_off_country_id = fields.Many2one(
        "res.country",
        domain=_get_drop_off_country_domain,
        string="Drop Off Country"
    )

    name = fields.Char(string='Name')
    customer_type = fields.Selection(
        [('individual', 'Individual'), ('company', 'Company')],
        string='Customer Type',
        default='individual',
    )
    my_company_id = fields.Many2one(
        "res.partner",
        domain="[('company_type', '=', 'company')]",
        string="Company"
    )
    if_change_Location = fields.Boolean()
    is_change_Location = fields.Boolean(default=False, readonly=True)
    change_Location = fields.Monetary(string="Change Location")

    is_extra_invoice_done = fields.Boolean()
    is_full_invoice_done = fields.Boolean()

    customer_mobile = fields.Char(string="Mobile")
    passport_no = fields.Char('ID / Passport No', store=True)
    passport_expiry = fields.Date('ID / Passport Expiry Date', store=True)
    nationality = fields.Many2one('res.country', string='Nationality', store=True)
    driver_expiry = fields.Date('Driving License Expiry Date', store=True)
    driving_number = fields.Char('Driving License No', store=True)
    date_of_birth = fields.Date(string="Date of Birth", store=True)
    age = fields.Integer(string="Age", store=True, related='customer_id.age')

    with_driver = fields.Boolean(string='With Additional Driver', required=False)
    additional_driver_details = fields.Many2one('res.partner', string="Additional Driver")
    additional_passport_no = fields.Char('ID / Passport No', store=True)
    additional_passport_expiry = fields.Date('ID / Passport Expiry Date', store=True)
    additional_nationality = fields.Many2one('res.country', string='Nationality', store=True)
    additional_driver_expiry = fields.Date('Driving License Expiry Date', store=True)
    additional_driving_number = fields.Char('Driving License No', store=True)
    additional_date_of_birth = fields.Date(string="Date of Birth", store=True)
    additional_age = fields.Integer(string="Age", store=True, related='additional_driver_details.age')
    additional_phone = fields.Char(string="Phone")
    additional_email = fields.Char(string="Email")
    check_in_odometer = fields.Float(string="Check In Odometer", copy=False)
    allowed_km_daily = fields.Float(string='Allowed KM Daily', store=True, related='booking_type.daily_allowed_km')
    allowed_km_all = fields.Float(string='Expected KM', compute='_compute_allowed_km_all')
    allowed_fuel_daily = fields.Float(string='Allowed Fuel', store=True, related='booking_type.daily_allowed_fuel')
    allowed_fuel_all = fields.Float(string='Expected Fuel', compute='_compute_allowed_km_all')
    booking_type = fields.Many2one('booking.type', string="Booking Type")
    last_fuel = fields.Float(string="Last Fuel", copy=False)
    fuel_ids = fields.One2many('fuel.vehicle', 'fuel_id', 'Fuel')
    odometer_ids = fields.One2many('odometer.vehicle', 'odometer_id', 'Odometer')
    check_in_fuel = fields.Float(string="Check In Fuel", copy=False)
    # rent_type = fields.Selection([('hour', "Hours"), ('days', "Days"), ('week', "Weeks"), ('month', "Months"),
    #                               ('year', "Years"), ('km', "Kilometers"), ('mi', 'Miles')], string="Rent Type")
    date_of_contract = fields.Datetime(string='Date of contract', required=True, index=True, copy=False,
                                       default=fields.Datetime.now)

    is_reserved = fields.Boolean(string='Is it reserved?', required=False)

    r_vehicle_id = fields.Many2one('fleet.vehicle', string="Replacement Vehicle",
                                   domain="[('id', 'not in', vehicle_ids), ('status', '=', 'available')]", copy=False)
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
    customer_id = fields.Many2one("res.partner", required=True, domain="[('parent_id', '=', my_company_id)]")


    @api.onchange('customer_type')
    def chang_customer_type(self):
        self.my_company_id = False
        self.customer_id = False

    @api.onchange('my_company_id')
    def chang_my_company_id(self):
        self.customer_id = False



    @api.onchange('start_date', 'end_date')
    def _compute_rent_type(self):
        for record in self:
            if record.start_date and record.end_date:
                duration = record.end_date - record.start_date
                if 1 <= duration.days < 7:
                    record.rent_type = 'days'
                elif 7 <= duration.days < 30:
                    record.rent_type = 'week'
                    print(duration.days)
                elif 30 <= duration.days < 365:
                    record.rent_type = 'month'
                    print(duration.days)
                elif duration.days >= 365:
                    record.rent_type = 'year'
                    print(duration.days)
                else:
                    # قم بتحديد سلوك افتراضي آخر هنا حسب الحاجة
                    record.rent_type = False

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
                rec.last_fuel = rec.vehicle_id.last_fuel
                rec.odometer_unit = rec.vehicle_id.odometer_unit
                rec.model_year = rec.vehicle_id.model_year
                rec.transmission = rec.vehicle_id.transmission
                rec.fuel_type = rec.vehicle_id.fuel_type
                rec.license_plate = rec.vehicle_id.license_plate
                self.fuel_ids = [(5, 0, 0)]
                self.fuel_ids = [(0, 0, {'vehicle_id': self.vehicle_id.id})]
                self.odometer_ids = [(5, 0, 0)]
                self.odometer_ids = [(0, 0, {'vehicle_id': self.vehicle_id.id})]

    @api.depends('allowed_km_daily', 'total_days')
    def _compute_allowed_km_all(self):
        for record in self:
            record.allowed_km_all = record.allowed_km_daily * record.duration_day
            record.allowed_fuel_all = record.allowed_fuel_daily * record.duration_day

    @api.onchange('rent_type')
    def onchange_rent_type(self):
        if self.rent_type:
            # Map rent_type to booking_type
            rent_type_mapping = {
                'hour': 'hour',
                'days': 'daily',
                'week': 'weekly',
                'month': 'monthly',
                'year': 'yearly',
                'km': 'km',
                'mi': 'mi'
            }
            booking_type_name = rent_type_mapping.get(self.rent_type)
            if booking_type_name:
                booking_type = self.env['booking.type'].search([('booking_type', '=', booking_type_name)], limit=1)
                if booking_type:
                    self.booking_type = booking_type.id

    def b_in_progress_to_c_return(self):
        return {
            'name': 'Vehicle Contract Wizard',
            'view_type': 'form',
            'view_mode': 'form',
            'res_model': 'vehicle.contract.wizard',
            'type': 'ir.actions.act_window',
            'target': 'new',
        }

    @api.onchange('customer_id')
    def get_customer_details(self):
        for rec in self:
            if rec.customer_id:
                rec.customer_phone = rec.customer_id.phone
                rec.customer_mobile = rec.customer_id.mobile
                rec.customer_email = rec.customer_id.email
                rec.passport_no = rec.customer_id.passport_no
                rec.passport_expiry = rec.customer_id.passport_expiry
                rec.nationality = rec.customer_id.nationality
                rec.driver_expiry = rec.customer_id.driver_expiry
                rec.driving_number = rec.customer_id.driving_number
                rec.date_of_birth = rec.customer_id.date_of_birth
            else:
                rec.customer_phone = False
                rec.customer_mobile = False
                rec.customer_email = False
                rec.passport_no = False
                rec.passport_expiry = False
                rec.nationality = False
                rec.driver_expiry = False
                rec.driving_number = False
                rec.date_of_birth = False

    @api.onchange('passport_no')
    def _compute_passport_no_from_partner(self):
        for order in self:
            order.customer_id.passport_no = order.passport_no

    @api.onchange('date_of_birth')
    def _compute_date_of_birth_from_partner(self):
        for order in self:

            # Calculate age from date of birth
            if order.date_of_birth:
                today = fields.Date.today()
                delta = today.year - order.date_of_birth.year - (
                        (today.month, today.day) < (order.date_of_birth.month, order.date_of_birth.day))
                order.customer_id.age = delta
                order.customer_id.date_of_birth = order.date_of_birth

    @api.onchange('passport_expiry')
    def _compute_passport_expiry_from_partner(self):
        for order in self:
            order.customer_id.passport_expiry = order.passport_expiry

    @api.onchange('nationality')
    def _compute_nationality_from_partner(self):
        for order in self:
            order.customer_id.nationality = order.nationality

    @api.onchange('driving_number')
    def _compute_driving_number_from_partner(self):
        for order in self:
            order.customer_id.driving_number = order.driving_number

    @api.onchange('driver_expiry')
    def _compute_driver_expiry_from_partner(self):
        for order in self:
            order.customer_id.driver_expiry = order.driver_expiry

    @api.constrains('age', 'additional_age')
    def _check_age(self):
        minimum_age = self.company_id.minimum_age
        maximum_age = self.company_id.maximum_age
        for record in self:
            if record.age < minimum_age:
                raise ValidationError(
                    "Contract cannot be completed due to age restriction for customer. Minimum age allowed is %s." % minimum_age)
            if record.age > maximum_age:
                raise ValidationError(
                    "Contract cannot be completed due to age restriction for customer. Maximum age allowed is %s." % maximum_age)
            if record.with_driver:
                if record.additional_age < minimum_age:
                    raise ValidationError(
                        "Contract cannot be completed due to age restriction for driver. Minimum age allowed is %s." % minimum_age)
                if record.additional_age > maximum_age:
                    raise ValidationError(
                        "Contract cannot be completed due to age restriction for driver. Maximum age allowed is %s." % maximum_age)

    @api.constrains('driver_expiry', 'additional_driver_expiry')
    def _check_driver_expiry(self):
        for record in self:
            if record.driver_expiry:
                expiry_date = fields.Date.from_string(record.driver_expiry)
                today = datetime.now().date()
                driving_certificate_deadline = self.company_id.driving_certificate_deadline
                if (expiry_date - today) <= timedelta(days=30):
                    raise ValidationError("The driving license for customer is expiring soon. Please renew.")
            if record.with_driver:
                if record.additional_driver_expiry:
                    expiry_date = fields.Date.from_string(record.additional_driver_expiry)
                    today = datetime.now().date()
                    if (expiry_date - today) <= timedelta(days=30):
                        raise ValidationError("The driving license for driver is expiring soon. Please renew.")

    @api.constrains('passport_expiry', 'additional_passport_expiry')
    def _check_passport_expiry(self):
        for record in self:
            if record.passport_expiry:
                expiry_date = fields.Date.from_string(record.passport_expiry)
                today = datetime.now().date()
                if (expiry_date - today) <= timedelta(days=30):
                    raise ValidationError("The Passport for customer is expiring soon. Please renew.")
            if record.with_driver:
                if record.additional_passport_expiry:
                    expiry_date = fields.Date.from_string(record.additional_passport_expiry)
                    today = datetime.now().date()
                    if (expiry_date - today) <= timedelta(days=30):
                        raise ValidationError("The Passport for driver is expiring soon. Please renew.")

    @api.onchange('additional_driver_details')
    def get_driver_details(self):
        for rec in self:
            if rec.additional_driver_details:
                rec.additional_phone = rec.additional_driver_details.phone
                rec.additional_email = rec.additional_driver_details.email
                rec.additional_passport_no = rec.additional_driver_details.passport_no
                rec.additional_passport_expiry = rec.additional_driver_details.passport_expiry
                rec.additional_nationality = rec.additional_driver_details.nationality
                rec.additional_driver_expiry = rec.additional_driver_details.driver_expiry
                rec.additional_driving_number = rec.additional_driver_details.driving_number
                rec.additional_date_of_birth = rec.additional_driver_details.date_of_birth
            else:
                rec.additional_phone = False
                rec.additional_email = False
                rec.additional_passport_no = False
                rec.additional_passport_expiry = False
                rec.additional_nationality = False
                rec.additional_driver_expiry = False
                rec.additional_driving_number = False
                rec.additional_date_of_birth = False

    @api.onchange('additional_passport_no')
    def _compute_passport_no_from_driver(self):
        for order in self:
            order.additional_driver_details.passport_no = order.additional_passport_no

    @api.onchange('additional_date_of_birth')
    def _compute_date_of_birth_from_driver(self):
        for order in self:

            # Calculate age from date of birth
            if order.additional_date_of_birth:
                today = fields.Date.today()
                delta = today.year - order.additional_date_of_birth.year - (
                        (today.month, today.day) < (
                    order.additional_date_of_birth.month, order.additional_date_of_birth.day))
                order.additional_driver_details.age = delta
                order.additional_driver_details.date_of_birth = order.additional_date_of_birth

    @api.onchange('additional_passport_expiry')
    def _compute_passport_expiry_from_driver(self):
        for order in self:
            order.additional_driver_details.passport_expiry = order.additional_passport_expiry

    @api.onchange('additional_nationality')
    def _compute_nationality_from_driver(self):
        for order in self:
            order.additional_driver_details.nationality = order.additional_nationality

    @api.onchange('additional_driving_number')
    def _compute_driving_number_from_driver(self):
        for order in self:
            order.additional_driver_details.driving_number = order.additional_driving_number

    @api.onchange('additional_driver_expiry')
    def _compute_driver_expiry_from_driver(self):
        for order in self:
            order.additional_driver_details.driver_expiry = order.additional_driver_expiry

    def view_car_replacement(self):
        return {
            'type': 'ir.actions.act_window',
            'name': _('Replacement'),
            'res_model': 'car.replacement',
            'domain': [('contract_id', '=', self.id)],
            'context': {
                'default_contract_id': self.id,
                'create': False,
            },
            'view_mode': 'tree,form',
            'target': 'current',
        }

    replacement_count = fields.Integer(compute='_compute_replacement_count')

    def _compute_replacement_count(self):
        for rec in self:
            replacement_count = self.env['car.replacement'].search_count([('contract_id', '=', rec.id)])
            rec.replacement_count = replacement_count
        return True

    def set_to_draft(self):
        self.write({'status': 'a_draft'})
        payment_options = self.env['vehicle.payment.option'].search([('vehicle_contract_id', '=', self.id)])
        payment_options.unlink()
        self.installment_created = False

    def action_create_final_invoice(self):
        vehicle_payment = self.env['vehicle.payment.option'].search([('vehicle_contract_id', '=', self.id)])
        extra_payment = self.env['extra.service'].search([('vehicle_contract_id', '=', self.id)])
        tax = []
        invoice_lines = []

        # Collect taxes from the vehicle contract
        for rec in vehicle_payment.vehicle_contract_id.tax_ids:
            tax.append(rec.id)

        # Process vehicle payments
        for rec in vehicle_payment:
            if rec.payment_amount == 0:
                message = {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'type': 'warning',
                        'message': "Please add the proper payment amount",
                        'sticky': False,
                    }
                }
                return message

            # Create invoice lines for vehicle payments

            payment_details = {
                'product_id': rec.invoice_item_id.id,
                'name': rec.name,
                'quantity': 1,
                'price_unit': rec.payment_amount,
                'tax_ids': tax,
            }
            invoice_lines.append((0, 0, payment_details))

        # Process extra services payments
        for extra_rec in extra_payment:
            # Create invoice lines for extra services
            extra_details = {
                'product_id': extra_rec.product_id.id,
                'name': extra_rec.product_id.name,
                'quantity': extra_rec.product_qty,
                'price_unit': extra_rec.amount,
                'tax_ids': tax,
            }
            invoice_lines.append((0, 0, extra_details))

        # Create invoice data
        # for rec in vehicle_payment:
        data = {
            'partner_id': self.customer_id.id,
            'move_type': 'out_invoice',

            'invoice_line_ids': invoice_lines,
            'vehicle_contract_id': self.id,
            'final': 'Final'
        }

        # Create invoice
        invoice_id = self.env['account.move'].sudo().create(data)
        self.invoice_id = invoice_id
        self.is_full_invoice_done = True

        # Return action to display created invoice
        return {
            'type': 'ir.actions.act_window',
            'name': _('Invoice'),
            'res_model': 'account.move',
            'res_id': invoice_id.id,
            'view_mode': 'form',
            'target': 'current'
        }

    def view_final_invoice(self):
        return {
            'type': 'ir.actions.act_window',
            'name': _('Final Invoices'),
            'res_model': 'account.move',
            'domain': [('vehicle_contract_id', '=', self.id), ('final', '=', 'Final')],
            'context': {
                'default_vehicle_contract_id': self.id,
                'create': False,
            },
            'view_mode': 'tree,form',
            'target': 'current',
        }

    invoice_final_count = fields.Integer(compute='_compute_final_count')

    def _compute_final_count(self):
        for rec in self:
            invoice_final_count = self.env['account.move'].search_count(
                [('vehicle_contract_id', '=', rec.id), ('final', '=', 'Final')])
            rec.invoice_final_count = invoice_final_count
        return True

    def action_create_extra_invoice(self):
        extra_payment = self.env['extra.service'].search([('vehicle_contract_id', '=', self.id)])
        tax = []
        invoice_lines = []
        for rec in extra_payment.vehicle_contract_id.tax_ids:
            tax.append(rec.id)
        for rec in extra_payment:
            if not rec:
                message = {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'type': 'warning',
                        'message': "No any Extra Services",
                        'sticky': False,
                    }
                }
                return message
            if rec.product_id.name in ['Extra KM', 'Extra Fuel']:
                extra_details = {
                    'product_id': rec.product_id.id,
                    'name': rec.product_id.name,
                    'quantity': rec.product_qty,
                    'price_unit': rec.amount,
                    'tax_ids': tax,
                }
                invoice_lines.append((0, 0, extra_details))
        current_date = datetime.now().date()
        data = {
            'partner_id': extra_payment.vehicle_contract_id.customer_id.id,
            'move_type': 'out_invoice',
            'invoice_date': current_date,
            'invoice_line_ids': invoice_lines,
            'vehicle_contract_id': extra_payment.vehicle_contract_id.id,
            'final': 'all'
        }
        invoice_id = self.env['account.move'].sudo().create(data)
        self.invoice_id = invoice_id
        self.is_extra_invoice_done = True
        return {
            'type': 'ir.actions.act_window',
            'name': _('Invoice'),
            'res_model': 'account.move',
            'res_id': invoice_id.id,
            'view_mode': 'form',
            'target': 'current'
        }

    duration_years = fields.Float(string="Duration (Years)", compute='_compute_duration', store=True)
    duration_months = fields.Float(string="Duration (Months)", compute='_compute_duration', store=True)
    duration_days = fields.Float(string="Duration (Days)", compute='_compute_duration', store=True)
    duration_day = fields.Float(string="Duration (Days)", compute='_compute_duration_day', store=True)
    is_any_damage = fields.Boolean(string="Any Damage")

    @api.depends('start_date', 'end_date')
    def _compute_duration(self):
        for contract in self:
            if contract.start_date and contract.end_date:
                start_date = fields.Datetime.from_string(contract.start_date)
                end_date = fields.Datetime.from_string(contract.end_date)
                delta = end_date - start_date
                years = delta.days // 365
                months = (delta.days % 365) // 30
                days = (delta.days % 365) % 30
                contract.duration_years = years
                contract.duration_months = months
                contract.duration_days = days
            else:
                contract.duration_years = 0
                contract.duration_months = 0
                contract.duration_days = 0

    @api.depends('start_date', 'end_date', 'rent_type')
    def _compute_duration_day(self):
        for contract in self:
            if contract.start_date and contract.end_date:
                start_date = fields.Datetime.from_string(contract.start_date)
                end_date = fields.Datetime.from_string(contract.end_date)

                if contract.rent_type == 'month':
                    # حساب عدد الأشهر بين التاريخين
                    delta = relativedelta(end_date, start_date)
                    full_months = delta.years * 12 + delta.months

                    # Check if there's a remaining part of a month
                    if delta.days > 0:
                        full_months += 1

                    # ضرب عدد الأشهر في 30 للحصول على عدد الأيام
                    contract.duration_day = full_months * 30
                else:
                    # حساب الفارق بالأيام
                    duration = end_date - start_date
                    contract.duration_day = duration.days
            else:
                contract.duration_day = 0

    def view_replace_invoice(self):
        return {
            'type': 'ir.actions.act_window',
            'name': _('replace Invoices'),
            'res_model': 'account.move',
            'domain': [('vehicle_contract_id', '=', self.id), ('final', '=', 'replace')],
            'context': {
                'default_vehicle_contract_id': self.id,
                'create': False,
            },
            'view_mode': 'tree,form',
            'target': 'current',
        }

    invoice_replace_count = fields.Integer(compute='_compute_replace_count')

    def _compute_replace_count(self):
        for rec in self:
            invoice_replace_count = self.env['account.move'].search_count(
                [('vehicle_contract_id', '=', rec.id), ('final', '=', 'replace')])
            rec.invoice_replace_count = invoice_replace_count
        return True

    def action_create_invoice_if_location_changed(self):
        invoice_lines = []
        product_change_Location = self.env['product.product'].search([('name', '=', 'Change Location')], limit=1)
        for rec in self:
            if rec.if_change_Location:
                if not rec.change_Location:
                    message = {
                        'type': 'ir.actions.client',
                        'tag': 'display_notification',
                        'params': {
                            'type': 'warning',
                            'message': "Please note: A rented Change Location is required.",
                            'sticky': False,
                        }
                    }
                    return message
                current_date = datetime.now().date()
                extra_details = {
                    'product_id': product_change_Location.id,
                    'name': 'Change Location',
                    'quantity': rec.change_Location,
                    'price_unit': rec.vehicle_id.rent_day,
                }
                invoice_lines.append((0, 0, extra_details))
                data = {
                    'partner_id': self.customer_id.id,
                    'move_type': 'out_invoice',
                    'invoice_date': current_date,
                    'invoice_line_ids': invoice_lines,
                    'vehicle_contract_id': self.id,
                }
                account_payment_id = self.env['account.move'].sudo().create(data)
                self.is_change_Location = True
