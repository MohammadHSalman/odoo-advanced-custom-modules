from odoo import models, fields, api, _

import json
import requests


class RefundOrder(models.Model):
    _inherit = 'pos.order'
    _description = 'Refund Order'

    def refund_order_pos(self):
        pos_order = self.env['pos.order'].search([], limit=1)
        if pos_order.amount_total < 0:
            verification = self.env['res.company'].search([], limit=1)
            token = verification.connection_pos()
            # url = 'https://frontoffice.tax.planetpayment.ae/services/transactions/api/v2/cancel-tax-refund-transaction'
            url = 'https://frontoffice.qa-tax.planetpayment.ae/services/transactions/api/v2/cancel-tax-refund-transaction'
            for i in pos_order.refunded_order_ids:
                tag_number = i.tag_number
            note = pos_order.note
            payload = {'tagNumber': '%s' % tag_number, 'note': '%s' % note}
            Authorization = 'Bearer %s' % token['access_token']
            req = requests.post(url, json=payload, headers={'Authorization': '%s' % Authorization})
            # print(json.loads(req.text)['message'],'+-+-')
            return json.loads(req.text)['message']

