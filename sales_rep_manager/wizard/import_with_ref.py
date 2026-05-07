from odoo import models, fields, api
from odoo.exceptions import UserError
import base64
import io
import pandas as pd


class RouteLineImportRefWizard(models.TransientModel):
    _name = 'route.line.import.ref.wizard'  # اسم موديل جديد كلياً
    _description = 'Import Customers to Route Line via Ref'

    # ملف Excel
    file = fields.Binary(string="Excel File", required=True)
    filename = fields.Char(string="File Name")

    # معلومات الخط
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
        # محاولة تعيين سوريا كافتراضي إذا كانت موجودة، وإلا تركها فارغة لتجنب الخطأ
        sy_country = self.env.ref('base.sy', raise_if_not_found=False)
        if sy_country:
            res['country_id'] = sy_country.id
        res['route_name'] = 'New Route'
        return res

    def action_import_customers(self):
        if not self.file:
            raise UserError("Please upload an Excel file.")

        # قراءة ملف Excel
        try:
            data = base64.b64decode(self.file)
            df = pd.read_excel(io.BytesIO(data))
        except Exception as e:
            raise UserError(f"Error reading file: {str(e)}")

        # التحقق من وجود الأعمدة المطلوبة
        # هنا نطلب وجود ref و Name
        if 'ref' not in df.columns:
            raise UserError("Excel file must contain a 'ref' column (Internal Reference).")

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
            if self.area_ids:
                route.area_ids = [(6, 0, self.area_ids.ids)]
            if self.sales_channel_ids:
                route.sales_channel_ids = [(6, 0, self.sales_channel_ids.ids)]

        found_partner_ids = []
        missing_partners = []

        # التكرار على الصفوف
        for index, row in df.iterrows():
            # 1. تجهيز الـ ref
            ref_val = row.get('ref')
            ref = False

            if not pd.isna(ref_val):
                ref = str(ref_val).strip()
                # تصحيح قراءة الأرقام من اكسل (مثلاً 100.0 تصبح 100)
                if ref.endswith('.0'):
                    ref = ref[:-2]

            # 2. تجهيز الاسم (كخيار احتياطي فقط إذا لم يوجد ref في ملف الاكسل)
            name_val = row.get('Name')
            name = str(name_val).strip() if not pd.isna(name_val) else False

            partner = False

            # الأولوية القصوى للبحث بـ REF
            if ref:
                partner = self.env['res.partner'].search([('ref', '=', ref)], limit=1)

            # إذا لم نجد العميل بالـ Ref، وكان الـ Ref فارغاً في الملف، نحاول بالاسم
            # (لكن إذا كان الـ Ref موجوداً ولم نجد العميل، لا نبحث بالاسم لنتجنب الخطأ)
            elif not ref and name:
                partner = self.env['res.partner'].search([('name', '=', name)], limit=1)

            if partner:
                found_partner_ids.append(partner.id)
            else:
                # لتتبع العملاء غير الموجودين (اختياري)
                missing_info = ref if ref else name
                missing_partners.append(missing_info)

        if not found_partner_ids:
            msg = "No customers found."
            if missing_partners:
                msg += f" Missing refs: {missing_partners[:5]}..."
            raise UserError(msg)

        # تحديث قائمة العملاء في المسار
        route.partner_ids = [(6, 0, found_partner_ids)]

        return {
            'type': 'ir.actions.client',
            'tag': 'reload',
        }