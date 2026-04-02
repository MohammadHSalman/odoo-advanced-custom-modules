from odoo import fields, models, api, _
from odoo.exceptions import UserError
from datetime import date
from datetime import datetime
from dateutil.relativedelta import relativedelta


class ResPartner(models.Model):
    """MHAZAS"""
    _inherit = 'res.partner'


    company_type = fields.Selection(
        string='Company Type',
        selection=[('person', 'Individual'), ('company', 'Company')],
        compute='_compute_company_type', inverse='_write_company_type',
        store=True
    )
    vat = fields.Char(string='VAT Number', index=True,
                      help="The Tax Identification Number. Values here will be validated based on the country format. You can use '/' to indicate that the partner is not subject to tax.")
    passport_no = fields.Char(string='ID / Passport No')
    nationality = fields.Many2one('res.country', string='Nationality', ondelete='restrict')
    passport_expiry = fields.Date(string='ID / Passport Expiry Date')
    driver_expiry = fields.Date(string='Driving License Expiry Date')
    is_vendor = fields.Boolean(string='Is Vendor?')
    driving_number = fields.Char(string='Driving License No')

    date_of_birth = fields.Date(string="Date of Birth")
    age = fields.Integer(string="Age", compute='_compute_age', store=True)

    @api.depends('date_of_birth')
    def _compute_age(self):
        today = datetime.today().date()
        for partner in self:
            if partner.date_of_birth:
                birth_date = datetime.strptime(str(partner.date_of_birth), '%Y-%m-%d').date()
                age = relativedelta(today, birth_date).years
                partner.age = age
            else:
                partner.age = 0

    vehicle_contract_count = fields.Integer(string='Vehicle Contracts', compute='_compute_vehicle_contract_count')

    def _compute_vehicle_contract_count(self):
        for partner in self:
            partner.vehicle_contract_count = self.env['vehicle.contract'].search_count(
                [('customer_id', '=', partner.id)])

    def action_view_vehicle_contracts(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Vehicle Contracts',
            'view_mode': 'tree,form',
            'res_model': 'vehicle.contract',
            'domain': [('customer_id', '=', self.id)],
            'context': dict(self.env.context, create=False)
        }
