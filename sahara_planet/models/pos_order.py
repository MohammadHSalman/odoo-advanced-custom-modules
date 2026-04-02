from odoo import models, fields, api, _
from odoo.exceptions import AccessDenied, ValidationError
# from odoo.exceptions import ValidationError, UserError

import requests
import json
import pytz


class AddFullOrder(models.Model):
    _inherit = 'pos.order'
    _description = 'Add Full Order'

    tag_number = fields.Char(string="Tag Number", readonly=True)
    tax_free = fields.Char(string='Tax Notes', readonly=True)
    tax_refund_status = fields.Char()
    tax_refund_qr_code = fields.Char()
    tax_message = fields.Char()
    tax_refund_status_code = fields.Float()
    refund_amount = fields.Float()
    tax_refund_excluded_items = fields.Char()


    @api.model
    def _order_fields(self, ui_order):
        res = super(AddFullOrder, self)._order_fields(ui_order)
        res['tax_free'] = ui_order['tax_free_pos'] if ui_order['tax_free_pos'] else False
        return res

    def send_order_pos(self):
        pos_order = self.env['pos.order'].search([], limit=1)
        verification = self.env['res.company'].search([], limit=1)
        if pos_order.tax_free == 'Tax free':
            token = verification.connection_pos()
            Authorization = 'Bearer %s' % token['access_token']
            if pos_order.amount_total < 0:

                url = 'https://frontoffice.tax.planetpayment.ae/services/transactions/api/v2/cancel-tax-refund-transaction'
                # url = 'https://frontoffice.qa-tax.planetpayment.ae/services/transactions/api/v2/cancel-tax-refund-transaction'
                for i in pos_order.refunded_order_ids:
                    if fields.Datetime.now().day - i.date_order.day < 90:
                        tag_number = i.tag_number
                    else:
                        tag_number = ''
                note = pos_order.note
                payload = {'tagNumber': '%s' % tag_number, 'note': '%s' % note}
                req = requests.post(url, json=payload, headers={'Authorization': '%s' % Authorization})
                if json.loads(req.text)['message'] == 11:
                    return json.loads(req.text)['message']
                elif json.loads(req.text)['message'] == 5:
                    return json.loads(req.text)['message']
                else:
                    return json.loads(req.text)['message']
            else:
                serialNumber = []
                url = 'https://frontoffice.tax.planetpayment.ae/services/transactions/api/v2/new-transaction'
                # url = 'https://frontoffice.qa-tax.planetpayment.ae/services/transactions/api/v2/new-transaction'
                pos_config = self.env['pos.config'].search([], limit=1)
                receiptNumber = pos_order.account_move.name
                date_order = pos_order.date_order.strftime('%Y-%m-%dT%H:%M')
                terminal = pos_config.terminal_code
                total = pos_order.amount_total
                vatIncl = pos_order.amount_tax
                totalBeforeVAT = total - vatIncl
                pm_code = pos_order.account_move.order_payment_method
                pm_name = pos_order.account_move.order_payment_method
                pm_total = pos_order.amount_total
                if pos_order.partner_id.firstName:
                    firstName = pos_order.partner_id.firstName
                else:
                    firstName = ''
                if pos_order.partner_id.lastName:
                    lastName = pos_order.partner_id.lastName
                else:
                    lastName = ''
                if pos_order.partner_id.country_nationality_id:
                    country_nationality_id = pos_order.partner_id.country_nationality_id
                else:
                    country_nationality_id = ''
                if pos_order.partner_id.country_residence_id:
                    country_residence_id = pos_order.partner_id.country_residence_id
                else:
                    country_residence_id = ''
                if pos_order.partner_id.phoneNumber:
                    phoneNumber = pos_order.partner_id.phoneNumber
                else:
                    phoneNumber = ''
                if pos_order.partner_id.birthDate:
                    birthDate = pos_order.partner_id.birthDate
                else:
                    birthDate = ''
                if pos_order.partner_id.issuedBy:
                    issuedBy = pos_order.partner_id.issuedBy
                else:
                    issuedBy = ''
                if pos_order.partner_id.passportNumber:
                    passportNumber = pos_order.partner_id.passportNumber
                else:
                    passportNumber = ''
                for s in pos_order.lines.pack_lot_ids:
                    if s.lot_name:
                        serialNumber.append(s.lot_name)
                    else:
                        serialNumber = []

                payload = {'issueTaxRefundTag': True, 'date': '%s' % date_order, 'receiptNumber': '%s' % receiptNumber,
                           'terminal': '%s' % terminal, 'taxFreeId': '', 'type': 'RECEIPT',
                           "order": {"totalBeforeVAT": '%s' % totalBeforeVAT, "vatIncl": '%s' % vatIncl,
                                     "total": '%s' % total,
                                     "items": [{"grossAmount": '%s' % i.price_total, "code": '', "departmentCode": '',
                                                "netAmount": '%s' % (i.price_unit * i.quantity),
                                                "description": '%s' % i.name,
                                                "discountAmount": None, "quantity": '%s' % i.quantity,
                                                "serialNumber": '%s' % serialNumber,
                                                "unitPrice": '%s' % i.price_unit, "vatRate": '5', "vatCode": '5',
                                                "vatAmount": '%s' % (i.price_total - (i.price_unit * i.quantity)),
                                                "merchandiseGroup": '121',
                                                "taxRefundEligible": True} for i in
                                               pos_order.account_move.invoice_line_ids],
                                     "paymentMethods": [{"code": '%s' % pm_code, "name": '%s' % pm_name,
                                                         "amount": '%s' % pm_total}]},
                           "shopper": {"firstName": '%s' % firstName, "lastName": '%s' % lastName,
                                       "nationality": '%s' % country_nationality_id,
                                       "countryOfResidence": '%s' % country_residence_id,
                                       "phoneNumber": '%s' % phoneNumber,
                                       "birth": {"date": '%s' % birthDate},
                                       "shopperIdentityDocument": {"type": 'PASSPORT',
                                                                   "issuedBy": '%s' % issuedBy,
                                                                   "number": '%s' % passportNumber}
                                       }

                           }
                print('**2', payload)
                try:
                    req = requests.post(url, json=payload, headers={'Authorization': '%s' % Authorization})

                    if req.ok:

                        tag_number = json.loads(req.text)['taxRefundResponse']['taxRefundTagNumber']
                        tax_refund_status = json.loads(req.text)['taxRefundResponse']['taxRefundStatus']
                        tax_refund_qr_code = json.loads(req.text)['taxRefundResponse']['taxRefundQrCode']
                        tax_message = json.loads(req.text)['taxRefundResponse']['message']
                        tax_refund_status_code = json.loads(req.text)['taxRefundResponse']['taxRefundStatusCode']
                        refund_amount = json.loads(req.text)['taxRefundResponse']['refundAmount']
                        tax_refund_excluded_items = json.loads(req.text)['taxRefundResponse']['taxRefundExcludedItems']
                        pos_order.sudo().tag_number = tag_number
                        pos_order.sudo().tax_refund_status = tax_refund_status
                        pos_order.sudo().tax_refund_qr_code = tax_refund_qr_code
                        pos_order.sudo().tax_message = tax_message
                        pos_order.sudo().tax_refund_status_code = tax_refund_status_code
                        pos_order.sudo().refund_amount = refund_amount
                        pos_order.sudo().tax_refund_excluded_items = tax_refund_excluded_items
                        pos_order.sudo().account_move.tag_num = tag_number
                        print(tag_number, '---------------------------------------------')
                        return "Tax-Free tag successfully %s" % tag_number
                    else:
                        # raise AccessDenied(_('%s' % json.loads(req.text)['message']))
                        return json.loads(req.text)['message']
                    # tag_number = ('No Tag Number %s' % json.loads(req.text)['message'])
                    # raise AccessDenied(_('%s' % json.loads(req.text)['message']))

                except:
                    pass

                #     print(self.tag_number, '))))))))', json.loads(req.text)['message'])
                #     req = requests.post(url, json=payload, headers={'Authorization': '%s' % Authorization})
                # #
                #     raise AccessDenied(_('%s' % json.loads(req.text)['message']))
                # return tag_number

    def get_tag(self):
        pos_order = self.env['pos.order'].search([], limit=1)

        tag_number = pos_order.tag_number
        print(tag_number, '.......................')
        return tag_number

    def _prepare_invoice_vals(self):
        vals = super()._prepare_invoice_vals()

        vals.update({'tag_num': self.tag_number})
        print('***************', vals['tag_num'])
        return vals
