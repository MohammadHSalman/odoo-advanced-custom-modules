from odoo import models, api
import logging

_logger = logging.getLogger(__name__)

class PosConfig(models.Model):
    _inherit = 'pos.config'

    # 1. Override the specific function you found
    @api.constrains('pricelist_id', 'use_pricelist', 'available_pricelist_ids', 'journal_id', 'invoice_journal_id', 'payment_method_ids')
    def _check_currencies(self):
        _logger.info("POS LEBANON: Bypassing _check_currencies validation")
        return

    # 2. Override the standard payment method check (Common in O17/O18)
    @api.constrains('payment_method_ids')
    def _check_payment_method_ids(self):
        _logger.info("POS LEBANON: Bypassing _check_payment_method_ids validation")
        return

    # 3. Override company currency check just in case
    @api.constrains('company_id', 'journal_id')
    def _check_company_journal(self):
        pass
