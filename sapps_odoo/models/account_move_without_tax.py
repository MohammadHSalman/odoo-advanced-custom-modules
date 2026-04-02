from odoo import api, fields, models, _
from odoo.exceptions import AccessError
import time
import requests
import uuid
import json
import pytz
from datetime import datetime, timedelta
import logging
import math

try:
    import qrcode
except ImportError:
    qrcode = None
try:
    import base64
except ImportError:
    base64 = None
from io import BytesIO
from odoo.exceptions import UserError

_logger = logging.getLogger('biometric_device')


class BillSuccessWizard(models.TransientModel):
    _name = 'bill.success.wizard'
    _description = 'رسالة نجاح الإرسال'

    message = fields.Text(string="الرسالة", readonly=True)

    def action_confirm_and_reload(self):
        """هذه الدالة تستدعى عند ضغط زر موافق"""
        # هذا الأمر يقوم بتحديث الصفحة الحالية (List View) ويغلق النافذة تلقائياً
        return {
            'type': 'ir.actions.client',
            'tag': 'reload',
        }


class AccountMove(models.Model):
    _inherit = 'account.move'

    consumer_spending_tax = fields.Monetary(string='Tax 5%', compute='_compute_zero_taxes')
    local_administration_tax = fields.Monetary(string='Tax 10% of tax', compute='_compute_zero_taxes')
    reconstruction_tax = fields.Monetary(string='Tax 5% of tax', compute='_compute_zero_taxes')
    qr_code = fields.Binary('QR Code', compute="_generate_qr")
    calculated_total = fields.Monetary(string="Calculated Total", compute="_compute_calculated_total")
    is_posted = fields.Boolean(string="Is Posted", copy=False)
    financial_status = fields.Char(string="Financial Status", default=" ", copy=False)
    code = fields.Char(string='Code', copy=False)
    code_uuid = fields.Char(string='Code UUID', copy=False)
    bill_date = fields.Char(string='Response Date', copy=False)
    date_bill = fields.Datetime(string='Date Bill', default=lambda self: fields.Datetime.now(), copy=False)
    random_number = fields.Char(string='Random Number', copy=False)

    # ---------------------------------------------------------
    # تم التغيير إلى توقيت دمشق ليطابق توقيت الفاتورة السورية
    # ---------------------------------------------------------
    tz = pytz.timezone('Asia/Damascus')

    printed = fields.Boolean(string="Printed", copy=False)
    sent_payload = fields.Text(string="Sent Payload Data", readonly=True, help="JSON Data sent to the API", copy=False)

    total_before_discount = fields.Monetary(
        string="Total Before Discount",
        compute="_compute_discount_values",
        store=False
    )

    discount_value = fields.Monetary(
        string="Discount Value",
        compute="_compute_discount_values",
        store=False
    )

    def _get_total_before_discount(self):
        self.ensure_one()
        lines = self.invoice_line_ids.filtered(lambda l: l.discount != 100)
        return sum(lines.mapped(lambda l: l.price_unit * l.quantity))

    def _get_discount_total(self):
        """Return total discount for the invoice, only for lines with discount != 100"""
        self.ensure_one()
        # فلترة الأسطر اللي فيها خصم فعلي وليست section/note
        lines = self.invoice_line_ids.filtered(lambda l: l.discount != 100)
        # مجموع قيمة الخصم لكل سطر
        return sum(line.price_unit * line.quantity * line.discount / 100 for line in lines)

    @api.depends(
        'invoice_line_ids',
        'invoice_line_ids.price_unit',
        'invoice_line_ids.quantity',
        'invoice_line_ids.discount',
        'amount_untaxed'
    )
    def _compute_discount_values(self):
        for move in self:
            total_before = move._get_total_before_discount()
            move.total_before_discount = total_before
            move.discount_value = move._get_discount_total()

    def make_it_printed(self):
        for rec in self:
            rec.printed = True

    @api.depends('amount_total')
    def _compute_zero_taxes(self):
        for rec in self:
            rec.consumer_spending_tax = 0.0
            rec.local_administration_tax = 0.0
            rec.reconstruction_tax = 0.0

    def _get_clean_bill_number(self):
        self.ensure_one()
        raw_number = self.mobile_invoice_number or self.name or ''
        return str(raw_number)

    # def send_bill(self):
    #     this = self
    #     self.ensure_one()
    #     clean_number = self._get_clean_bill_number()
    #     sent_invoice = self.env['sent.invoices'].search([('invoice_number', '=', clean_number)], limit=1)
    #     if sent_invoice:
    #         return
    #     elif this.state != 'posted':
    #         return
    #     elif this.move_type != 'out_invoice':
    #         return
    #     if not self.code_uuid:
    #         self.code_uuid = str(uuid.uuid4())
    #     user = this.env['tax.verification'].search([], limit=1)
    #     if not user:
    #         return
    #     token = user.connection()
    #     # url = 'http://185.216.133.4/liveapi/api/Bill/AddFullBill'
    #     # url = 'http://213.178.227.75/Taxapi/api/Bill/AddFullBill'
    #     url = 'http://185.216.133.12/Taxapi/api/Bill/AddFullBill'
    #
    #     # ---------------------------------------------------------
    #     # الحل: تحويل وقت قاعدة البيانات (UTC) إلى توقيت دمشق
    #     # ---------------------------------------------------------
    #     # 1. تعريف الوقت على أنه UTC
    #     utc_time = pytz.utc.localize(this.create_date)
    #     # 2. تحويله إلى التوقيت المحلي (دمشق)
    #     local_time = utc_time.astimezone(self.tz)
    #
    #     amount_total = this._get_total_before_discount()
    #
    #     # نرسل الوقت المحلي بالتنسيق النصي (بدون فواصل UTC لضمان ظهوره كما هو)
    #     payload = {
    #         'billValue': amount_total,
    #         'billNumber': clean_number,
    #         'code': this.code_uuid,
    #         'currency': this.currency_id.name,
    #         'exProgram': 'SAPPS - Odoo',
    #         'date': local_time.strftime('%Y-%m-%dT%H:%M:%S')  # سيرسل 2026-02-28T08:45:00
    #     }
    #
    #     try:
    #         r = requests.post(url, json=payload, headers={'Authorization': '%s' % token})
    #         if r.ok:
    #             response_json = r.json()
    #             if 'data' in response_json:
    #                 data_content = response_json['data']
    #                 code = data_content.get('code')
    #                 bill_date = data_content.get('billDate')
    #                 random_number = data_content.get('randomNumber')
    #
    #                 this.sudo().is_posted = True
    #                 this.sudo().financial_status = 'Posted to Finance'
    #                 this.sudo().code = code
    #                 this.sudo().bill_date = bill_date
    #                 this.sudo().random_number = random_number
    #                 self.env['sent.invoices'].create({'invoice_number': clean_number})
    #                 this.env.cr.commit()
    #             else:
    #                 _logger.error(f"Bill sent but response format unexpected for {clean_number}. Response: {r.text}")
    #         else:
    #             _logger.error(f"Failed to send bill {clean_number}. Response: {r.text}")
    #     except Exception as e:
    #         _logger.error(f"Error in send_bill for {clean_number}: {str(e)}")
    def send_bill(self):
        # 1. التأكد من التعامل مع سجل واحد
        self.ensure_one()

        # ---------------------------------------------------------
        # قفل السجل (Database Locking)
        # ---------------------------------------------------------
        try:
            self.env.cr.execute("SELECT id FROM account_move WHERE id = %s FOR UPDATE NOWAIT", [self.id])
        except Exception:
            _logger.warning(f"Invoice {self.id} is currently locked/processing. Skipping duplicate request.")
            return

        # ---------------------------------------------------------
        # التعديل لـ Odoo 18
        # نستخدم invalidate_recordset بدلاً من invalidate_cache
        # ---------------------------------------------------------
        self.invalidate_recordset(['is_posted', 'financial_status', 'code_uuid'])
        # ---------------------------------------------------------

        # التحقق من الحالة
        if self.is_posted or self.financial_status == 'Posted to Finance':
            return

        clean_number = self._get_clean_bill_number()

        # تحقق إضافي من جدول الأرشيف
        if self.env['sent.invoices'].search_count([('invoice_number', '=', clean_number)]):
            return

        if self.move_type != 'out_invoice':
            return

        # ---------------------------------------------------------
        # تثبيت UUID
        # ---------------------------------------------------------
        if not self.code_uuid:
            generated_uuid = str(uuid.uuid4())
            self.env.cr.execute("UPDATE account_move SET code_uuid = %s WHERE id = %s", (generated_uuid, self.id))
            self.code_uuid = generated_uuid

        # باقي الكود لاستدعاء البيانات
        user = self.env['tax.verification'].search([], limit=1)
        if not user:
            return
        token = user.connection()

        # الروابط
        url = 'http://185.216.133.12/Taxapi/api/Bill/AddFullBill'

        utc_time = pytz.utc.localize(self.create_date)
        local_time = utc_time.astimezone(self.tz)
        amount_total = self._get_total_before_discount()

        # تجهيز البيانات
        payload = {
            'billValue': amount_total,
            'billNumber': clean_number,
            'code': self.code_uuid,
            'currency': self.currency_id.name,
            'exProgram': 'SAPPS - Odoo',
            'date': local_time.strftime('%Y-%m-%dT%H:%M:%S')
        }

        try:
            # إرسال الطلب
            r = requests.post(url, json=payload, headers={'Authorization': '%s' % token})

            if r.ok:
                response_json = r.json()
                if 'data' in response_json:
                    data_content = response_json['data']

                    # تحديث البيانات بعد النجاح
                    self.sudo().write({
                        'is_posted': True,
                        'financial_status': 'Posted to Finance',
                        'code': data_content.get('code'),
                        'bill_date': data_content.get('billDate'),
                        'random_number': data_content.get('randomNumber'),
                        'sent_payload': json.dumps(payload, ensure_ascii=False)
                    })

                    if not self.env['sent.invoices'].search_count([('invoice_number', '=', clean_number)]):
                        self.env['sent.invoices'].create({'invoice_number': clean_number})

                    self.env.cr.commit()
                else:
                    _logger.error(f"Bill sent but response format unexpected for {clean_number}. Response: {r.text}")
            else:
                _logger.error(f"Failed to send bill {clean_number}. Response: {r.text}")

        except Exception as e:
            _logger.error(f"Error in send_bill for {clean_number}: {str(e)}")

    def write(self, vals):
        forbidden_fields = [
            'invoice_line_ids', 'partner_bank_id', 'company_id', 'invoice_incoterm_id', 'incoterm_location',
            'partner_id', 'invoice_date_due',
            'invoice_date',
            'currency_id',
            'journal_id',
            'ref', 'team_id', 'invoice_user_id',
        ]
        for move in self:
            if move.financial_status == 'Posted to Finance':
                if 'financial_status' in vals or 'sent_payload' in vals or 'code' in vals:
                    continue
                illegal_changes = [f for f in vals if f in forbidden_fields]
                if illegal_changes:
                    raise UserError(
                        _("عذراً، الفاتورة مرسلة للمالية.\n"
                          "يمكنك تسجيل الدفعات، ولكن لا يمكنك تعديل البيانات الأساسية.")
                    )
        return super(AccountMove, self).write(vals)

    # def send_multi_bill(self):
    #     invoices = self
    #     success_count = 0
    #     chunk_size = 5
    #
    #     # معالجة الفواتير
    #     for i in range(0, len(invoices), chunk_size):
    #         chunk = invoices[i:i + chunk_size]
    #         for invoice in chunk:
    #             already_posted = invoice.is_posted
    #             try:
    #                 invoice.send_bill()
    #                 if not already_posted and invoice.is_posted:
    #                     success_count += 1
    #             except Exception as e:
    #                 _logger.error(f"Error sending invoice {invoice.id}: {e}")
    #
    #     # تجهيز نص الرسالة
    #     msg_text = _("Operation completed successfully.\nInvoices sent: %s") % success_count
    #
    #     # إنشاء النافذة المنبثقة
    #     wizard = self.env['bill.success.wizard'].create({'message': msg_text})
    #
    #     # فتح النافذة
    #     return {
    #         'title': _('Finance Submission Result'),
    #         'type': 'ir.actions.act_window',
    #         'res_model': 'bill.success.wizard',
    #         'res_id': wizard.id,
    #         'view_mode': 'form',
    #         'target': 'new',  # عرض كنافذة منبثقة
    #     }
    def send_multi_bill(self):
        # فلترة الفواتير
        invoices_to_process = self.filtered(lambda inv:
                                            not inv.is_posted and
                                            inv.financial_status != 'Posted to Finance' and
                                            inv.move_type == 'out_invoice'
                                            )

        success_count = 0
        chunk_size = 5

        for i in range(0, len(invoices_to_process), chunk_size):
            chunk = invoices_to_process[i:i + chunk_size]
            for invoice in chunk:
                was_posted = invoice.is_posted

                try:
                    invoice.send_bill()

                    # ---------------------------------------------------------
                    # التعديل لـ Odoo 18
                    # ---------------------------------------------------------
                    invoice.invalidate_recordset(['is_posted'])
                    # ---------------------------------------------------------

                    if invoice.is_posted and not was_posted:
                        success_count += 1
                except Exception as e:
                    _logger.error(f"Error sending invoice {invoice.id}: {e}")

        msg_text = _("Operation completed successfully.\nInvoices sent: %s") % success_count

        wizard = self.env['bill.success.wizard'].create({'message': msg_text})

        return {
            'title': _('Finance Submission Result'),
            'type': 'ir.actions.act_window',
            'res_model': 'bill.success.wizard',
            'res_id': wizard.id,
            'view_mode': 'form',
            'target': 'new',
        }

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not vals.get('code_uuid'):
                vals['code_uuid'] = str(uuid.uuid4())

        records = super(AccountMove, self).create(vals_list)
        return records

    def _generate_qr(self):
        user_company = self.env.user.company_id
        if not user_company:
            raise UserError(_('No company data found for the current user.'))
        vat = user_company.vat
        facility_name = user_company.name
        pos_num_acc = user_company.pos_num_acc

        if not pos_num_acc:
            main_company = self.env['res.company'].browse(1)
            if main_company.exists():
                pos_num_acc = main_company.pos_num_acc

        for rec in self:
            clean_num = rec._get_clean_bill_number()
            amount_total = rec._get_total_before_discount()

            # تحويل الوقت في الـ QR Code ليطابق الإرسال
            utc_time_qr = pytz.utc.localize(rec.create_date)
            local_time_qr = utc_time_qr.astimezone(self.tz)

            if qrcode and base64:
                qr = qrcode.QRCode(
                    version=1,
                    error_correction=qrcode.constants.ERROR_CORRECT_L,
                    box_size=3,
                    border=4,
                )
                qr.add_data("#")
                qr.add_data(vat)
                qr.add_data("_")
                qr.add_data(facility_name)
                qr.add_data("_")
                qr.add_data(pos_num_acc or '')
                qr.add_data("#")
                qr.add_data(clean_num)
                qr.add_data("_")
                # استخدام الوقت المحلي المحول
                qr.add_data(local_time_qr.strftime('%Y-%m-%d/%H:%M:%S'))
                qr.add_data("_")
                qr.add_data(amount_total)
                qr.add_data("_")
                qr.add_data(rec.currency_id.name)
                qr.add_data("_")
                qr.add_data("SAPPS Odoo")
                qr.add_data("#")
                qr.add_data(rec.code_uuid)
                qr.add_data("#")
                qr.make(fit=True)
                img = qr.make_image()
                temp = BytesIO()
                img.save(temp, format="PNG")
                qr_image = base64.b64encode(temp.getvalue())

                rec.qr_code = qr_image
            else:
                raise UserError(_('Necessary Requirements To Run This Operation Is Not Satisfied'))

    @api.depends('invoice_line_ids', 'invoice_line_ids.discount')
    def _compute_calculated_total(self):
        for move in self:
            move.calculated_total = sum(
                line.quantity * line.price_unit for line in move.invoice_line_ids if line.discount != 100)
