from odoo import models, fields


class LocationCar(models.Model):
    _name = 'location.car'
    _description = 'Location Car'
    _rec_name = "country_id"

    country_id = fields.Many2one("res.country")
