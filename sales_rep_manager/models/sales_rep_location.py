from datetime import datetime, timedelta

from odoo import models, fields, api


class SalesRepLocation(models.Model):
    _name = 'sales.rep.location'
    _description = 'Sales Rep GPS Location'
    _order = 'location_time desc'

    sales_rep_id = fields.Many2one('sales.rep.profile', string='Sales Representative', required=True, index=True,
                                   ondelete='cascade')
    latitude = fields.Float(digits=(10, 7), required=True)
    longitude = fields.Float(digits=(10, 7), required=True)
    location_time = fields.Datetime(string='Send Time', required=True, index=True)

    @api.model
    def _gc_location_history(self):
        days_to_keep = 30

        limit_date = datetime.now() - timedelta(days=days_to_keep)

        old_records = self.search([('location_time', '<', limit_date)])
        count = len(old_records)
        if count > 0:
            old_records.unlink()

        import logging
        _logger = logging.getLogger(__name__)
        _logger.info(f"Cleaned {count} old sales representative location records.")
