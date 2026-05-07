# -*- coding: utf-8 -*-
from odoo import fields, models, api
import qrcode
import base64
from io import BytesIO

class AccountMove(models.Model):
    _inherit = "account.move"

    mobile_invoice_number = fields.Char(
        string="Mobile Invoice Number",
        index=True,
        help="Local invoice number coming from the mobile app."
    )

    invoice_cash_rounding_id = fields.Many2one('account.cash.rounding')

    @api.model
    def default_get(self, fields_list):
        # جلب القيم الافتراضية الأساسية
        res = super(AccountMove, self).default_get(fields_list)

        move_type = self.env.context.get('default_move_type')

        if move_type in ['out_invoice', 'out_refund']:
            rounding_method = self.env['account.cash.rounding'].search(
                [('name', '=', 'NAD Cash Rounding')],
                limit=1
            )
            if rounding_method:
                res['invoice_cash_rounding_id'] = rounding_method.id

        return res

    qr_code_image = fields.Binary(
        string="QR Code",
        compute='_compute_qr_code_image',
        store=True
    )

    @api.depends('amount_total', 'invoice_date', 'invoice_user_id', 'state')
    def _compute_qr_code_image(self):
        for record in self:
            if not record.invoice_date or not record.company_id:
                record.qr_code_image = False
                continue

            vat = record.company_id.vat or ''
            inv_date = str(record.invoice_date)
            total = str(record.amount_total)
            currency = record.currency_id.name or ''


            rep_seq = ''
            if record.invoice_user_id:
                profile = self.env['sales.rep.profile'].sudo().search(
                    [('user_id', '=', record.invoice_user_id.id)], limit=1
                )
                if profile and profile.sequence:
                    rep_seq = profile.sequence

            qr_content = f"#{vat}_NAD_001#Odooinvoice_{inv_date}_{total}_#{currency}_odoo_18#{rep_seq}"

            try:
                qr = qrcode.QRCode(
                    version=1,
                    error_correction=qrcode.constants.ERROR_CORRECT_L,
                    box_size=10,
                    border=4,
                )
                qr.add_data(qr_content)
                qr.make(fit=True)

                img = qr.make_image(fill_color="black", back_color="white")
                temp = BytesIO()
                img.save(temp, format="PNG")
                qr_image = base64.b64encode(temp.getvalue())

                record.qr_code_image = qr_image
            except Exception as e:
                record.qr_code_image = False

