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


class AccountMove(models.Model):
    _inherit = 'account.move'

    qr_code = fields.Binary('QR Code', compute="_generate_qr")
    calculated_total = fields.Monetary(string="Calculated Total", compute="_compute_calculated_total")
    is_posted = fields.Boolean(string="Is Posted")
    financial_status = fields.Char(string="Financial Status", default=" ")
    code = fields.Char(string='Code')
    code_uuid = fields.Char(string='Code UUID')
    bill_date = fields.Char(string='Response Date')
    date_bill = fields.Datetime(string='Date Bill', default=lambda self: fields.Datetime.now())
    random_number = fields.Char(string='Random Number')
    consumer_spending_tax = fields.Monetary(string='Tax 5%', compute='_consumer_spending_tax')
    local_administration_tax = fields.Monetary(string='Tax 10% of tax', compute='_local_administration_tax')
    reconstruction_tax = fields.Monetary(string='Tax 5% of tax', compute='_reconstruction_tax')
    tz = pytz.timezone('Europe/Moscow')
    custom_invoice_number = fields.Char(string='Invoice Number', readonly=True, copy=False)
    printed = fields.Boolean(string="Printed")
    sent_payload = fields.Text(string="Sent Payload Data", readonly=True, help="JSON Data sent to the API")

    def make_it_printed(self):
        for rec in self:
            rec.printed = True

    def update_code_uuid_for_existing_invoices(self):
        existing_invoices = self.env['account.move'].search([])
        for invoice in existing_invoices:
            if not invoice.code_uuid:
                invoice.sudo().write({'code_uuid': str(uuid.uuid4())})

    def send_bill(self):
        this = self
        sent_invoice = self.env['sent.invoices'].search([('invoice_number', '=', this.custom_invoice_number)])
        if sent_invoice:
            return
        elif this.state != 'posted':
            return
        elif this.move_type != 'out_invoice':
            return

        this.update_code_uuid_for_existing_invoices()
        user = this.env['tax.verification'].search([], limit=1)
        token = user.connection()
        url = 'http://185.216.133.4/liveapi/api/Bill/AddFullBill'
        # url = 'http://213.178.227.75/Taxapi/api/Bill/AddFullBill'
        local_time = pytz.utc.localize(this.date_bill).astimezone(self.tz)
        order_pos = self.env['account.move'].browse(self.id)
        amount_total = sum(line.price_unit * line.quantity for line in order_pos.invoice_line_ids)
        payload = {'billValue': amount_total, 'billNumber': this.custom_invoice_number, 'code': this.code_uuid,
                   'currency': this.currency_id.name, 'exProgram': 'SAPPS - Odoo',
                   'date': (local_time.isoformat())}
        try:
            r = requests.post(url, json=payload, headers={'Authorization': '%s' % token})
            code = json.loads(r.text)['data']['code']
            bill_date = json.loads(r.text)['data']['billDate']
            random_number = json.loads(r.text)['data']['randomNumber']
            if r.ok:
                this.sudo().is_posted = True
                this.sudo().financial_status = 'Posted to Finance'
                this.sudo().code = code
                this.sudo().bill_date = bill_date
                this.sudo().random_number = random_number
                this.env.cr.commit()
                self.env['sent.invoices'].create({'invoice_number': this.custom_invoice_number})
            else:
                raise AccessError(
                    _("The invoice cannot be sent. Please check that the connection is correct and try again"))
        except:
            pass

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

    def send_multi_bill(self):
        invoices = self
        chunk_size = 5
        for i in range(0, len(invoices), chunk_size):
            chunk = invoices[i:i + chunk_size]
            for invoice in chunk:
                sent_invoice = self.env['sent.invoices'].search(
                    [('invoice_number', '=', invoice.custom_invoice_number)])
                if sent_invoice:
                    continue
                elif invoice.state != 'posted':
                    continue
                elif invoice.move_type != 'out_invoice':
                    continue
                invoice.update_code_uuid_for_existing_invoices()
                user = self.env['tax.verification'].search([], limit=1)
                token = user.connection()
                url = 'http://185.216.133.4/liveapi/api/Bill/AddFullBill'
                # url = 'http://213.178.227.75/Taxapi/api/Bill/AddFullBill'
                local_time = pytz.utc.localize(invoice.date_bill).astimezone(self.tz)
                amount_total = sum(line.price_unit * line.quantity for line in invoice.invoice_line_ids)
                payload = {
                    'billValue': amount_total,
                    'billNumber': invoice.custom_invoice_number,
                    'code': invoice.code_uuid,
                    'currency': invoice.currency_id.name,
                    'exProgram': 'Odoo ERP',
                    'date': local_time.isoformat()
                }
                print(payload)
                try:
                    response = requests.post(url, json=payload, headers={'Authorization': '%s' % token})
                    if response.ok:
                        response_data = json.loads(response.text)['data']
                        m_code = response_data['code']
                        m_bill_date = response_data['billDate']
                        m_random_number = response_data['randomNumber']
                        invoice.sudo().is_posted = True
                        invoice.sudo().financial_status = 'Posted to Finance'
                        invoice.sudo().code = m_code
                        invoice.sudo().bill_date = m_bill_date
                        invoice.sudo().random_number = m_random_number
                        self.env.cr.commit()
                        self.env['sent.invoices'].create({'invoice_number': invoice.clean_name})
                    else:
                        raise AccessError(
                            _("The invoice cannot be sent. Please check that the connection is correct and try again"))
                except Exception as e:
                    _logger.error("An error occurred while sending the invoice: %s", str(e))

    @api.model
    def run_send_invoice_to_finance(self):
        today = datetime.now()
        last_month_end = today.replace(day=1, hour=0, minute=0, second=0, microsecond=0) - timedelta(seconds=1)
        domain = [
            ('state', '=', 'posted'),
            ('code', '=', False),
            ('random_number', '=', False),
            ('invoice_date', '<=', last_month_end.strftime("%Y-%m-%d"))
        ]
        bills_to_send = self.env['account.move'].search(domain)
        for bill in bills_to_send:
            success = False
            while not success:
                try:
                    bill.send_bill()
                    success = True
                except Exception as e:
                    error_message = "For 'Moode2261' An error occurred while sending the invoice: %s" % str(e)
                    _logger.error(error_message)
                    print(error_message)
                    time.sleep(3600)

    def _round_tax(self, value, currency):
        if currency.name == 'SYP':
            return int(math.ceil(value))
        else:
            return int(math.ceil(value))

    def _consumer_spending_tax(self):
        for record in self:
            tax = self.env['account.tax'].search([('unique_tax_num', '=', '0.05')])
            if record.amount_untaxed >= 0:
                tax = (record.amount_untaxed * (tax.amount / 100))
                tax = self._round_tax(tax, record.currency_id)
                record.consumer_spending_tax = tax

    def _local_administration_tax(self):
        for record in self:
            tax = self.env['account.tax'].search([('unique_tax_num', '=', '0.25')])
            if record.amount_untaxed >= 0:
                tax2 = (record.amount_untaxed * (tax.amount / 100))
                tax2 = self._round_tax(tax2, record.currency_id)
                record.local_administration_tax = tax2

    def _reconstruction_tax(self):
        for record in self:
            tax = self.env['account.tax'].search([('unique_tax_num', '=', '0.5')])
            if record.amount_untaxed >= 0:
                tax3 = (record.amount_untaxed * (tax.amount / 100))
                tax3 = self._round_tax(tax3, record.currency_id)
                record.reconstruction_tax = tax3

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not vals.get('code_uuid'):
                vals['code_uuid'] = str(uuid.uuid4())

            if vals.get('move_type') == 'out_invoice':
                last_invoice = self.search([
                    ('move_type', '=', 'out_invoice'),
                    ('custom_invoice_number', '!=', False)
                ], order='custom_invoice_number desc', limit=1)

                if last_invoice and last_invoice.custom_invoice_number.isdigit():
                    last_number = int(last_invoice.custom_invoice_number)
                else:
                    last_number = 0

                vals['custom_invoice_number'] = str(last_number + 1).zfill(6)

        records = super(AccountMove, self).create(vals_list)
        return records

    def _generate_qr(self):
        user_company = self.env.user.company_id
        if not user_company:
            raise UserError(_('No company data found for the current user.'))
        vat = user_company.vat
        facility_name = user_company.name
        pos_num_acc = user_company.pos_num_acc
        for rec in self:
            order_pos = rec.env['account.move'].browse(rec.id)
            amount_total = sum(line.price_unit * line.quantity for line in order_pos.invoice_line_ids)
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
                qr.add_data(pos_num_acc)
                qr.add_data("#")
                qr.add_data(rec.custom_invoice_number)
                qr.add_data("_")
                qr.add_data(rec.date_bill)
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
                rec.update({'qr_code': qr_image})
            else:
                raise UserError(_('Necessary Requirements To Run This Operation Is Not Satisfied'))

    @api.depends('invoice_line_ids', 'consumer_spending_tax', 'local_administration_tax', 'reconstruction_tax')
    def _compute_calculated_total(self):
        for move in self:
            untaxed_amount = sum(line.quantity * line.price_unit for line in move.invoice_line_ids)
            move.calculated_total = untaxed_amount + move.consumer_spending_tax + move.local_administration_tax + move.reconstruction_tax
