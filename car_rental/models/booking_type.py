from odoo import models, api, fields, _
from odoo.exceptions import ValidationError


class BookingType(models.Model):
    """MHAZAS"""
    _name = 'booking.type'
    _rec_name = "booking_type"

    booking_type = fields.Selection(selection=[('hour', "Hours"),
                                               ('daily', 'Days'),
                                               ('weekly', 'Weeks'),
                                               ('monthly', 'Months'),
                                               ('yearly', 'Years'), ('km', "Kilometers"), ('mi', 'Miles')
                                               ], string='Rent Type', required=True, help='Select the Booking type',
                                    unique=True)

    days_no = fields.Float(string='# of Days', required=True)
    allowed_km = fields.Float(string='Allowed KM', required=True)

    daily_allowed_km = fields.Float(string='Daily Allowed KM', compute='_compute_daily_allowed_km', store=True,
                                    readonly=True)

    allowed_fuel = fields.Float(string='Allowed Fuel')

    daily_allowed_fuel = fields.Float(string='Daily Allowed Fuel', compute='_compute_daily_allowed_km', store=True,
                                      readonly=True)

    @api.depends('allowed_km', 'days_no', 'allowed_fuel')
    def _compute_daily_allowed_km(self):
        for record in self:
            if record.days_no != 0:
                record.daily_allowed_km = record.allowed_km / record.days_no
                record.daily_allowed_fuel = record.allowed_fuel / record.days_no
            else:
                record.daily_allowed_km = 0.0
                record.daily_allowed_fuel = 0.0

    @api.onchange('booking_type')
    def _onchange_booking_type(self):
        for record in self:
            if record.booking_type == 'daily':
                record.days_no = 1
            elif record.booking_type == 'weekly':
                record.days_no = 7
            elif record.booking_type == 'monthly':
                record.days_no = 31
            elif record.booking_type == 'yearly':
                record.days_no = 365

    @api.constrains('booking_type')
    def _check_unique_booking_type(self):
        for record in self:
            existing_records = self.env['booking.type'].search([('booking_type', '=', record.booking_type)])
            if len(existing_records) > 1:
                raise ValidationError(_('This option cannot be selected again because it already exists.'))
