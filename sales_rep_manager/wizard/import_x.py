from odoo import models, fields, api
from odoo.exceptions import UserError
import base64
import io
import pandas as pd

class RouteLineImportWizard(models.TransientModel):
    _name = 'route.line.import.wizard'
    _description = 'Import Customers to Route Line'

    # ملف Excel يحتوي فقط أسماء العملاء
    file = fields.Binary(string="Excel File", required=True)
    filename = fields.Char(string="File Name")

    # معلومات الخط يتم إدخالها من الويزرد
    route_number = fields.Char(string="Route Number", required=True)
    route_name = fields.Char(string="Route Name", required=True)
    country_id = fields.Many2one('res.country', string="Country", required=True)
    governorate_id = fields.Many2one('res.country.state', string="Governorate", required=True)
    area_ids = fields.Many2many('res.city', string="Areas",
                                domain="[('state_id', '=', governorate_id)]")
    sales_channel_ids = fields.Many2many('res.partner.industry', string="Sales Channels")

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        res['country_id'] = self.env.ref('base.sy').id  # افتراض سوريا
        res['route_name'] = 'New Route'
        return res

    def action_import_customers(self):
        if not self.file:
            raise UserError("Please upload an Excel file.")

        # قراءة ملف Excel
        data = base64.b64decode(self.file)
        df = pd.read_excel(io.BytesIO(data))

        # تحقق من وجود عمود Name
        if 'Name' not in df.columns:
            raise UserError("Excel file must contain 'Name' column with customer names.")

        # البحث أو إنشاء Route Line
        route = self.env['route.line'].search([('route_number', '=', self.route_number)], limit=1)
        if not route:
            route_vals = {
                'route_number': self.route_number,
                'route_name': self.route_name,
                'country_id': self.country_id.id,
                'governorate_id': self.governorate_id.id,
                'area_ids': [(6, 0, self.area_ids.ids)] if self.area_ids else [],
                'sales_channel_ids': [(6, 0, self.sales_channel_ids.ids)] if self.sales_channel_ids else [],
                'company_id': self.env.company.id,
            }
            route = self.env['route.line'].create(route_vals)
        else:
            # تحديث المناطق وقنوات المبيعات إذا موجودة
            if self.area_ids:
                route.area_ids = [(6, 0, self.area_ids.ids)]
            if self.sales_channel_ids:
                route.sales_channel_ids = [(6, 0, self.sales_channel_ids.ids)]

        # البحث عن العملاء في res.partner
        customer_names = df['Name'].dropna().unique().tolist()
        customers = self.env['res.partner'].search([('name', 'in', customer_names)])

        if not customers:
            raise UserError("No matching customers found in the system.")

        # إضافة العملاء إلى Route Line
        route.partner_ids = [(6, 0, customers.ids)]

        return {
            'type': 'ir.actions.client',
            'tag': 'reload',
        }
