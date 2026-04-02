# داخل odx_freshchat_connector/models/odx_freshchat_connector.py
from odoo import api, fields, models, _

class FreshchatConnector(models.Model):
    _inherit = "odx.freshchat.connector"

    # الإعدادات الافتراضية لإرسال استبيان الشحن عبر واتساب
    survey_id = fields.Many2one(
        "survey.survey",
        string="Default Survey for Shipments",
        tracking=True,
        help="The survey that will be used by default when shipments are delivered."
    )
    whatsapp_template_id = fields.Many2one(
        "odx.whatsapp.template",
        string="Default WhatsApp Template (Survey)",
        tracking=True,
        help="The WhatsApp template used to push the survey link to the customer."
    )

    def get_active_connector(self):
        """أقرب كونّكتور فعّال نستخدمه كإعداد عام."""
        return self.search([("active", "=", True)], limit=1)
