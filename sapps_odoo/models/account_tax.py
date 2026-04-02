from odoo import models, fields, api, _
from odoo.exceptions import ValidationError
from math import ceil


class AccountTax(models.Model):
    _inherit = 'account.tax'

    # -------------------------------------------------------------------------
    # 1. تعريف الحقول (كما في الكود القديم)
    # -------------------------------------------------------------------------
    rounding = fields.Integer(string='Rounding', required=True, default=1, tracking=True)
    unique_tax_num = fields.Float(string='Unique')

    # -------------------------------------------------------------------------
    # 2. قيود التحقق (Constraints)
    # -------------------------------------------------------------------------
    @api.constrains('rounding')
    def _check_rounding_value(self):
        for record in self:
            if record.rounding <= 0:
                raise ValidationError(_("Rounding value must be a positive integer greater than zero."))
            # ملاحظة: في Odoo حقول Integer دائماً تعيد int، لكن هذا التحقق لا يضر
            if not isinstance(record.rounding, int):
                raise ValidationError(_("Rounding value must be an integer."))

    # -------------------------------------------------------------------------
    # 3. منطق التقريب المخصص (SYP 100 / Others Ceil)
    # -------------------------------------------------------------------------
    def _round_amount_based_on_currency(self, amount, currency):
        """
        دالة مساعدة لتطبيق منطق التقريب:
        - ليرة سورية (SYP): التقريب لأقرب 100 للأعلى (سقف).
        - عملات أخرى: التقريب لأقرب 1 صحيح للأعلى.
        """
        # إذا لم يتم تمرير عملة، نستخدم التقريب العادي (السقف)
        if not currency:
            return ceil(amount)

        if currency.name == 'S.P':
            return ceil(amount)
        else:
            # مثال: 1.1 -> 2.0
            return ceil(amount)

    # -------------------------------------------------------------------------
    # 4. تجاوز دالة الحساب الرئيسية في Odoo 18
    # -------------------------------------------------------------------------
    @api.model
    def _add_tax_details_in_base_line(self, base_line, company, rounding_method=None):
        """
        في Odoo 18، هذه الدالة هي المسؤولة عن تجميع وحساب الضرائب لكل سطر.
        نقوم بتجاوزها لتعديل الأرقام بعد حسابها وقبل تخزينها، لتطبيق التقريب القسري.
        """

        # أولاً: استدعاء الدالة الأصلية ليقوم Odoo بالحسابات القياسية
        super(AccountTax, self)._add_tax_details_in_base_line(base_line, company, rounding_method)

        # ثانياً: استخراج البيانات التي تم حسابها
        # base_line: هو قاموس يحتوي على العملة والمبالغ وتفاصيل الضرائب
        currency = base_line['currency_id']
        tax_details = base_line['tax_details']

        # ملاحظة: القيم التي تنتهي بـ _currency هي المبالغ بعملة الفاتورة (وهي التي تهمنا للتقريب)

        # --- الخطوة 1: تطبيق التقريب على المبلغ الأساسي (Base / Total Excluded) ---
        # نتحقق من السياق كما كان في الكود القديم
        if self._context.get('round_base', True):
            raw_base = tax_details['raw_total_excluded_currency']
            rounded_base = self._round_amount_based_on_currency(raw_base, currency)

            # تحديث القيم في القاموس
            tax_details['raw_total_excluded_currency'] = rounded_base
            tax_details['total_excluded_currency'] = rounded_base

        # --- الخطوة 2: تطبيق التقريب على مبالغ الضرائب (Tax Amounts) ---
        total_tax_amount_calc = 0.0

        for tax_data in tax_details['taxes_data']:
            # أ) تقريب مبلغ الضريبة
            raw_tax = tax_data['raw_tax_amount_currency']
            rounded_tax = self._round_amount_based_on_currency(raw_tax, currency)

            tax_data['raw_tax_amount_currency'] = rounded_tax
            tax_data['tax_amount_currency'] = rounded_tax

            # ب) تقريب مبلغ الأساس الخاص بهذه الضريبة
            raw_tax_base = tax_data['raw_base_amount_currency']
            rounded_tax_base = self._round_amount_based_on_currency(raw_tax_base, currency)

            tax_data['raw_base_amount_currency'] = rounded_tax_base
            tax_data['base_amount_currency'] = rounded_tax_base

            # ج) تجميع إجمالي الضرائب الجديد لحساب الإجمالي الشامل لاحقاً
            # (نتجاهل الضرائب العكسية Reverse Charge لأنها لا تؤثر على الصافي المستحق عادة)
            if not tax_data.get('is_reverse_charge'):
                total_tax_amount_calc += rounded_tax

        # --- الخطوة 3: إعادة حساب الإجمالي الشامل (Total Included) ---
        # المعادلة الصحيحة: الإجمالي الشامل = الأساس المقرب + مجموع الضرائب المقربة
        new_total_excluded = tax_details['raw_total_excluded_currency']
        new_total_included = new_total_excluded + total_tax_amount_calc

        tax_details['raw_total_included_currency'] = new_total_included
        tax_details['total_included_currency'] = new_total_included

        # الآن أصبح base_line جاهزاً ويحتوي على الأرقام المقربة حسب منطقك
        # وسيقوم Odoo باستخدامه تلقائياً في compute_all وفي إنشاء القيود