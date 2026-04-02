# -*- coding: utf-8 -*-
import datetime
import time

import pytz
import qrcode
import base64
from io import BytesIO
from odoo import models, fields, api, _
from odoo.exceptions import UserError, AccessError
import requests
import logging

_logger = logging.getLogger(__name__)


class PosOrder(models.Model):
    _inherit = 'pos.order'
    _description = 'Add Full Order'

    state = fields.Selection(selection_add=[('send', 'Posted to Finance')], ondelete={'send': 'cascade'})
    financial_condition = fields.Char("Financial condition", default='Not deported')
    check = fields.Integer("Check")
    code = fields.Char(string='Code')
    code_uuid = fields.Char(string='Code UUID')
    order_date = fields.Char(string='Order Date')
    random_number = fields.Char(string='Random Number')
    qr_code_pos = fields.Binary('QR Code', compute="_generate_qr_pos")
    reprint_count = fields.Integer(string='Reprint Count', default=0)
    create_time = fields.Char(string="Create Time", readonly=True)

    def _export_for_ui(self, order):
        fields = super()._export_for_ui(order)
        fields['reprint_count'] = order.reprint_count
        fields['create_time'] = order.create_time
        return fields

    @api.model
    def _order_fields(self, ui_order):
        res = super(PosOrder, self)._order_fields(ui_order)
        res['code_uuid'] = ui_order.get('code_uuid_v4')
        res['reprint_count'] = ui_order.get('reprint_count', 0)
        res['create_time'] = ui_order.get('create_time')
        return res

    @api.model
    def create_from_ui(self, orders, draft=False):
        order_ids = []
        for order in orders:
            existing_order = self.env['pos.order'].search(
                ['|', '|', ('id', '=', order['data'].get('server_id')),
                 ('pos_reference', '=', order['data'].get('name')),
                 ('code_uuid', '=', order['data'].get('code_uuid_v4'))],
                limit=1)
            if (existing_order and existing_order.state == 'draft') or not existing_order:
                order_ids.append(self._process_order(order, draft, existing_order))

        return self.env['pos.order'].search_read(domain=[('id', 'in', order_ids)],
                                                 fields=['id', 'pos_reference', 'code_uuid'])

    def send_order(self):
        # تحقق مما إذا كانت القيم موجودة بالفعل في الحقول 'code' و 'random_number'
        if self.code and self.random_number:
            return  # تجاوز تنفيذ الوظيفة دون أي إشعار أو رسالة

        user = self.env['tax.verification'].search([], limit=1)
        token = user.connection()

        order_pos = self.env['pos.order'].browse(self.id)
        amount_total = sum(line.price_unit * line.qty for line in order_pos.lines)

        payload = {
            'billValue': amount_total,
            'billNumber': str(self.id),  # استخدام id بدلاً من pos_reference
            'code': self.code_uuid,
            'currency': self.currency_id.name,
            'exProgram': 'SAPPS - Odoo',
            'date': self.date_order.isoformat(),
        }
        print(payload)

        url = 'http://185.216.133.4/liveapi/api/Bill/AddFullBill'
        try:
            r = requests.post(url, json=payload, headers={'Authorization': f'{token}'})
            r.raise_for_status()  # Raise an error for bad HTTP responses

            response_data = r.json().get('data', {})
            self.sudo().write({
                'financial_condition': 'Deported',
                'check': 1,
                'code': response_data.get('code'),
                'order_date': response_data.get('billDate'),
                'random_number': response_data.get('randomNumber'),
                'state': 'send'
            })

        except requests.exceptions.RequestException as e:
            raise AccessError(_("The invoice cannot be sent. Please check the connection and try again: %s" % str(e)))

    def _generate_qr_pos(self):
        user = self.env.company
        vat = user.vat or ""
        facility_name = user.name or ""

        user_tz = self.env.user.tz or pytz.utc
        local = pytz.timezone(user_tz)
        fmt_date = '%Y/%m/%d'

        for rec in self:
            if not qrcode or not base64:
                raise UserError(_('Necessary libraries for generating QR code are missing.'))

            total_amount = sum(line.price_unit * line.qty for line in rec.lines)

            # إزالة كلمة "Order" من بداية `pos_reference` وإزالة الفراغات و `-`
            sanitized_pos_reference = rec.pos_reference.replace('Order', '').replace(' ', '').replace('-', '').lstrip()

            qr_data = (
                f"#{vat}_{facility_name}_{rec.session_id.config_id.pos_num}_{rec.id} # "
                f"{rec.date_order.astimezone(local).strftime(fmt_date)}_{total_amount}_{rec.currency_id.name}_"
                f"SAPPS Odoo #{rec.code_uuid}#"
            )

            qr = qrcode.QRCode(
                version=1,
                error_correction=qrcode.constants.ERROR_CORRECT_L,
                box_size=3,
                border=4,
            )
            qr.add_data(qr_data)
            qr.make(fit=True)

            img = qr.make_image(fill_color="black", back_color="white")
            temp = BytesIO()
            img.save(temp, format="PNG")
            qr_image = base64.b64encode(temp.getvalue())
            rec.qr_code_pos = qr_image

    @api.model
    def run_send_order_to_finance(self):
        today = datetime.now()
        last_month_end = today.replace(day=1, hour=0, minute=0, second=0, microsecond=0) - timedelta(seconds=1)
        domain = [
            ('state', '=', 'posted'),
            ('code', '=', False),
            ('random_number', '=', False),
            ('date_order', '<=', last_month_end.strftime("%Y-%m-%d"))
        ]
        orders_to_send = self.env['pos.order'].search(domain)
        for order in orders_to_send:
            success = False
            while not success:
                try:
                    order.send_order()
                    success = True
                except Exception as e:
                    error_message = "For 'Moode2261' An error occurred while sending the order: %s" % str(e)
                    _logger.error(error_message)
                    print(error_message)
                    time.sleep(3600)
