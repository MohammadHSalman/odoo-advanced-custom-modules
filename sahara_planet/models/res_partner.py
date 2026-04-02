# -*- coding: utf-8 -*-

from odoo import api, fields, models


class Partner(models.Model):
    _name = 'res.partner'
    _inherit = 'res.partner'

    code = fields.Char(string='Code', tracking=True)
    firstName = fields.Char(string='First Name', tracking=True)
    lastName = fields.Char(string='Last Name', tracking=True)
    gender = fields.Selection([
        ('male', 'Male'),
        ('female', 'Female'),
    ], string="Gender", tracking=True)
    phoneNumber = fields.Char(string='Phone Number', tracking=True)
    passportNumber = fields.Char(string='Passport Number', tracking=True)
    expirationDate = fields.Date(string='Expiration Date', tracking=True)
    birthDate = fields.Date(string='Birth Date', tracking=True)
    # country_nationality_id = fields.Many2one(
    #     'res.country', 'Nationality', tracking=True)
    country_nationality_id = fields.Char(
        'Nationality', tracking=True)
    # country_residence_id = fields.Many2one(
    #     'res.country', 'Country Of Residence', tracking=True)
    country_residence_id = fields.Char(
        'Country Of Residence', tracking=True)
    country_birth_id = fields.Many2one(
        'res.country', 'Place Of Birth', tracking=True)
    # issuedBy = fields.Many2one(
    #     'res.country', 'Issued By', tracking=True)
    issuedBy = fields.Char(
        'Issued By', tracking=True)
