# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import AccessError, ValidationError
from odoo.tools import safe_eval

import requests
import logging

_logger = logging.getLogger(__name__)


class TaxVerification(models.Model):
    _name = 'tax.verification'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _description = 'Tax Verification'
    _rec_name = 'userName'

    userName = fields.Char(string='User Name',  tracking=True, required=True)
    passWord = fields.Char(string='Password',  tracking=True, required=True)
    company_vat = fields.Char(string='Tax ID',  tracking=True, required=True)
    state = fields.Selection([
        ('draft', 'Not Confirmed'),
        ('done', 'Confirmed'),
    ], string='Status', index=True, readonly=True, copy=False, default='draft')

    _sql_constraints = [
        ('unique_record', 'UNIQUE(id)', 'Only one record is allowed in Settings!')
    ]

    @api.model_create_multi
    def create(self, vals_list):
        if self.search_count([]) >= 1:
            raise ValidationError(_(
                'You can only create one contact information record. '
                'An existing record is already present, and additional records cannot be added.'
            ))
        return super(TaxVerification, self).create(vals_list)

    # def _get_company_vat(self):
    #     """ Helper method to get the company's VAT number from the cache or database """
    #     _company_vat_cache = self.env['res.company'].search([], limit=1).vat
    #     return _company_vat_cache


    def connection(self):
        # vat = self._get_company_vat()
        # url = 'http://185.216.133.4/liveapi/api/account/AccountingSoftwarelogin'
        # url = 'https://213.178.227.75/Taxapi/api/account/login'# Use HTTPS for secure connection
        url = 'http://185.216.133.12/Taxapi/api/account/AccountingSoftwarelogin'

        payload = {
            'userName': self.userName,
            'passWord': self.passWord,
            'taxNumber': self.company_vat,
        }
        _logger.error("API request failed>>>>>>>>>>>>>>>>>>>>>: %s",payload)

        try:
            r = requests.post(url, json=payload, timeout=10)
            r.raise_for_status()  # Raises HTTPError for bad responses (4XX, 5XX)

            response_data = r.json()
            if 'data' in response_data and 'token' in response_data['data']:
                token = response_data['data']['token']
                self.write({'state': 'done'})
                return token
            else:
                raise AccessError(_("Unexpected response structure: %s") % response_data)

        except requests.exceptions.Timeout:
            raise AccessError(_("The connection timed out. Please try again later."))

        except requests.exceptions.RequestException as e:
            _logger.error("API request failed: %s", str(e))
            raise AccessError(_("No connection. Check that the connection information is correct or try again later."))

        except Exception as e:
            _logger.exception("Unexpected error during API call: %s", str(e))
            raise AccessError(_("An unexpected error occurred: %s") % str(e))
