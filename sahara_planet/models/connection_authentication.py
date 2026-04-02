# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import AccessError

import requests
import json


class Company(models.Model):
    _name = 'res.company'
    _inherit = 'res.company'

    client_id = fields.Char(string="Planet ID")
    client_secret = fields.Char(string="Planet secret")

    def connection_pos(self):
        company_field = self.env['res.company'].search([], limit=1)
        client_id = company_field.client_id
        secret = company_field.client_secret
        url = 'https://auth.tax.planetpayment.ae/auth/realms/planet/protocol/openid-connect/token'
        # url = 'https://auth.qa-tax.planetpayment.ae/auth/realms/planet/protocol/openid-connect/token'
        payload = {'client_id': '%s' % client_id, 'client_secret': '%s' % secret, 'grant_type': 'client_credentials'}

        try:
            request = requests.post(url, data=payload)

            token = request.json()
            return token
        except:
            raise AccessError(_("No connection.Please contact the manager to confirm contact information..."))
