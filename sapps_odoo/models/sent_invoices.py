
# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
import logging

_logger = logging.getLogger('sent_invoice_logger')


class SentInvoices(models.Model):
    _name = 'sent.invoices'
    _description = 'Sent Invoices'


    invoice_number = fields.Char(string='Sent Invoice Number')