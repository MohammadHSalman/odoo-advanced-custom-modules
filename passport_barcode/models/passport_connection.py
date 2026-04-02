# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import AccessError

import requests
import json


class PassportConnection(models.Model):
    _name = 'res.partner'
    _inherit = 'res.partner'


    passport_barcode = fields.Text(string='Passport Barcode')

    def Passport_Connection(self):
        company_field = self.env['res.company'].search([], limit=1)
        client_id = company_field.client_id
        secret = company_field.client_secret
        url = 'https://auth.tax.planetpayment.ae/auth/realms/planet/protocol/openid-connect/token'
        payload = {'client_id': '%s' % client_id, 'client_secret': '%s' % secret, 'grant_type': 'client_credentials'}

        try:
            request = requests.post(url, data=payload)
            request.raise_for_status()  # Raise an exception for non-successful response codes (e.g., 4xx or 5xx)

            token = request.json()
            return token
        except requests.exceptions.RequestException as e:
            error_message = str(e)
            raise AccessError(_(error_message))

    def passport_information(self):
        # verification = self.env['res.company'].search([], limit=1)
        token = self.Passport_Connection()
        print('token', token)
        Authorization = 'Bearer %s' % token['access_token']
        print('Authorization', Authorization)
        url = 'https://frontoffice.tax.planetpayment.ae/services/transactions/api/v2/mrz-decoded'
        self.passport_barcode = self.passport_barcode[::-1].replace('\n', '', self.passport_barcode.count('\n') - 1)[::-1].replace('\n', '\r\n', 1)
        payload = {"mrz": self.passport_barcode}
        print('payload', payload)
        try:
            requset = requests.post(url, json=payload, headers={'Authorization': '%s' % Authorization})
            print('requset', requset.text)
            firstName = json.loads(requset.text)['firstName']
            lastName = json.loads(requset.text)['lastName']
            nationality = json.loads(requset.text)['nationality']
            countryOfResidence = json.loads(requset.text)['countryOfResidence']
            number = json.loads(requset.text)['shopperIdentityDocument']['number']
            issuedBy = json.loads(requset.text)['shopperIdentityDocument']['issuedBy']
            birth = json.loads(requset.text)['birth']['date']
            print(nationality)
            if requset.ok:
                # Create a new record in the sent.invoices table


                self.sudo().firstName = firstName
                self.sudo().lastName = lastName
                self.sudo().country_nationality_id = nationality
                self.sudo().passportNumber = number
                self.sudo().country_residence_id = countryOfResidence
                self.sudo().issuedBy = issuedBy
                self.sudo().birthDate = birth

            else:

                response_data = json.loads(requset.text)
                error_message = response_data.get("message", "Unknown error")
                raise AccessError(_(error_message))
        except:
            response_data = json.loads(requset.text)
            error_message = response_data.get("message", "Unknown error")
            raise AccessError(_(error_message))
