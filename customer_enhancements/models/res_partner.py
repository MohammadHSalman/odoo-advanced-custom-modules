# -*- coding: utf-8 -*-
from odoo import fields, models, api
from odoo.exceptions import ValidationError


class ResPartner(models.Model):
    _inherit = "res.partner"

    # customer_classification = fields.Selection(
    #     selection=[
    #         ("A", "A"),
    #         ("B", "B"),
    #         ("C", "C"),
    #     ],
    #     string="Customer Classification",
    #     help="Optional classification tier for the customer.",
    #     tracking=True,
    #     index=True,
    #     required=False,
    #     default=False,
    # )
    state_id = fields.Many2one(
        'res.country.state', required=True)
    # industry_id = fields.Many2one(
    #     'res.partner.industry',
    #     string='Industry',
    #     required=True,
    #     tracking=True,
    # )
    @api.constrains('customer_rank', 'industry_id')
    def _check_industry_if_customer(self):
        for record in self:
            if record.customer_rank > 0 and not record.industry_id:
                raise ValidationError("The 'Industry' field is required for customers (customer_rank > 0).")

    property_account_receivable_id = fields.Many2one('account.account', tracking=True,)
    property_product_pricelist = fields.Many2one(
        comodel_name='product.pricelist',
        tracking=True,
    )

    company_id = fields.Many2one(default=lambda self: self.env.company)

    def _get_default_country(self):
        country = self.env['res.country'].search([('code', '=', 'SY')], limit=1)
        return country.id if country else False

    country_id = fields.Many2one(
        'res.country',
        default=_get_default_country
    )

    def _get_default_category_ids(self):

        company_name = self.env.company.name
        tag_name = False

        keyword_map = {
            'دمشق': 'زبائن فرع دمشق',
            'حلب': 'زبائن فرع حلب',
            'اللاذقية': 'زبائن فرع اللاذقية',
            'حمص': 'زبائن فرع حمص',
            'طرطوس': 'زبائن فرع طرطوس',
            'السويداء': 'زبائن فرع السويداء',
            'درعا': 'زبائن فرع درعا',
            'حماة': 'زبائن فرع حماة',
        }

        for keyword, target_tag in keyword_map.items():
            if keyword in company_name:
                tag_name = target_tag
                break

        if not tag_name:
            tag_name = f"زبائن {company_name}"

        # البحث عن التاج في قاعدة البيانات
        if tag_name:
            category = self.env['res.partner.category'].search([('name', '=', tag_name)], limit=1)
            if category:
                return [category.id]

        return []

    category_id = fields.Many2many(
        'res.partner.category',
        column1='partner_id',
        column2='category_id',
        string='Tags',
        default=_get_default_category_ids
    )
    # @api.constrains('name')
    # def _check_unique_partner_name(self):
    #     for record in self:
    #         if record.name:
    #
    #             domain = [
    #                 ('name', '=ilike', record.name),
    #                 ('id', '!=', record.id)
    #             ]
    #
    #             existing_partner = self.search(domain, limit=1)
    #
    #             if existing_partner:
    #                 raise ValidationError(f"اسم الشريك/العميل '{record.name}' موجود مسبقاً! يرجى اختيار اسم فريد.")
