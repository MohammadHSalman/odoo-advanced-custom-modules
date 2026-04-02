from odoo import models, api, fields, _


class CarCategory(models.Model):
    """MHAZAS"""
    _name = 'car.category'
    _description = 'CarCategory'
    _rec_name = 'name'

    name = fields.Char()
