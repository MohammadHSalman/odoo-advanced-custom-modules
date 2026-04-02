try:
    import qrcode
except ImportError:
    qrcode = None
try:
    import base64
except ImportError:
    base64 = None
from io import BytesIO
from odoo import models, fields, api, _
from odoo.exceptions import UserError


class Product(models.Model):
    """ inherit Invoice to add report settings """
    _inherit = "account.move"

    qr_code = fields.Binary('QRcode', compute="_generate_qr")

    def _generate_qr(self):
        planet = self.env["pos.order"].search([], limit=1)
        tag_number = planet.tag_number
        tax_refund_status = planet.tax_refund_status
        tax_refund_qr_code = planet.tax_refund_qr_code
        tax_message = planet.tax_message
        tax_refund_status_code = planet.tax_refund_status_code
        refund_amount = planet.refund_amount
        tax_refund_excluded_items = planet.tax_refund_excluded_items
        "method to generate QR code"
        for rec in self:
            if qrcode and base64:

                qr = qrcode.QRCode(
                    version=1,
                    error_correction=qrcode.constants.ERROR_CORRECT_L,
                    box_size=8,
                    border=8,
                )

                qr.add_data("taxRefundTagNumber: ")
                qr.add_data(tag_number)
                qr.add_data("\n")
                qr.add_data("taxRefundStatus: ")
                qr.add_data(tax_refund_status)
                qr.add_data("\n")
                qr.add_data("taxRefundQrCode: ")
                qr.add_data(tax_refund_qr_code)
                qr.add_data("\n")
                qr.add_data("refundAmount: ")
                qr.add_data(refund_amount)
                qr.add_data("\n")
                qr.add_data("message: ")
                qr.add_data(tax_message)
                qr.add_data("\n")
                qr.add_data("taxRefundStatusCode: ")
                qr.add_data(tax_refund_status_code)
                qr.add_data("\n")
                qr.add_data("taxRefundExcludedItems: ")
                qr.add_data(tax_refund_excluded_items)

                qr.make(fit=True)
                img = qr.make_image()
                temp = BytesIO()
                img.save(temp, format="PNG")
                qr_image = base64.b64encode(temp.getvalue())
                rec.update({'qr_code': qr_image})
            else:
                raise UserError(_('Necessary Requirements To Run This Operation Is Not Satisfied'))
