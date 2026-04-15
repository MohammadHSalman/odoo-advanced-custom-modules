# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import ValidationError
import re


class SalesRepOnboarding(models.Model):
    _name = 'sales.rep.onboarding'
    _description = 'Sales Representative Onboarding Request'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _rec_name = "expected_username"

    state = fields.Selection([
        ('draft', 'Draft'),
        ('done', 'Processed')
    ], string='Status', default='draft', tracking=True)

    name_ar = fields.Char(string="Name (Arabic)", required=True, tracking=True)
    first_name_en = fields.Char(string="First Name (English)", required=True)
    last_name_en = fields.Char(string="Last Name (English)", required=True)

    company_id = fields.Many2one('res.company', string='Branch (Company)', default=lambda self: self.env.company,
                                 required=True)

    rep_type = fields.Selection([
        ('cashvan', 'CashVan'),
        ('presales', 'PreSales')
    ], string="Sales Team", required=True, default='cashvan')

    presales_location_id = fields.Many2one(
        'stock.location',
        string="PreSales Location",
        domain="[('company_id', '=', company_id), ('usage', '=', 'internal'), "
               "('name', 'not ilike', 'cars'), ('scrap_location', '=', False)]",
        help="Select a location for PreSales (excluding CARS locations and scrap locations)"
    )

    expected_username = fields.Char(
        string="Expected Username",
        store=True,
        readonly=False,
        tracking=True,
        required=True
    )

    username_available = fields.Boolean(
        string="Username Available",
        compute="_compute_username_availability",
        store=False
    )

    username_warning = fields.Char(
        string="Username Warning",
        compute="_compute_username_availability",
        store=False
    )

    attachment_mandatory = fields.Boolean(
        string='Is the attachment mandatory?',
        default=False,
        tracking=True,
        help="If checked, attachments will be mandatory for this sales representative."
    )

    allow_manual_offer = fields.Boolean(
        string='Allow manual offer',
        default=False,
        tracking=True,
        help="Allow the sales representative to create manual offers."
    )

    allow_usd_payment = fields.Boolean(
        string='Allow USD payment',
        default=True,
        tracking=True,
        help="Allow the sales representative to accept USD payments."
    )

    allowed_distance_m = fields.Float(
        string="Allowed Distance (meters)",
        default=0.0,
        tracking=True,
        help="Maximum allowed distance in meters for this sales representative."
    )

    operation_type_id = fields.Many2one(
        'stock.picking.type',
        string='Operation Type',
        check_company=True,
        copy=False,
        tracking=True,
        domain="[('company_id', '=', company_id), ('sequence_code', 'in', ['PS-OUT', 'CV-OUT'])]",
        help="Select the operation type for delivery operations (PS-OUT for PreSales, CV-OUT for CashVan)"
    )

    @api.constrains('name_ar')
    def _check_name_ar_language(self):
        for rec in self:
            if rec.name_ar:
                if not re.match(r'^[\u0600-\u06FF\s\-]+$', rec.name_ar):
                    raise ValidationError(
                        _("The Arabic Name must contain ONLY Arabic characters and spaces. (No English letters or numbers)."))

    @api.constrains('first_name_en', 'last_name_en')
    def _check_name_en_language(self):
        for rec in self:
            if rec.first_name_en:
                if not re.match(r"^[A-Za-z\s\-']+$", rec.first_name_en):
                    raise ValidationError(
                        _("The First Name (English) must contain ONLY English characters. (No Arabic letters or numbers)."))

            if rec.last_name_en:
                if not re.match(r"^[A-Za-z\s\-']+$", rec.last_name_en):
                    raise ValidationError(
                        _("The Last Name (English) must contain ONLY English characters. (No Arabic letters or numbers)."))

    @api.onchange('company_id')
    def _onchange_company_id(self):
        self.presales_location_id = False
        self.operation_type_id = False

    @api.onchange('rep_type', 'company_id')
    def _onchange_rep_type_suggest_operation(self):
        if self.rep_type and self.company_id:
            if self.rep_type == 'cashvan':
                sequence_code = 'CV-OUT'
            else:
                sequence_code = 'PS-OUT'

            suggested_op_type = self.env['stock.picking.type'].search([
                ('company_id', '=', self.company_id.id),
                ('sequence_code', '=', sequence_code)
            ], limit=1)

            if suggested_op_type:
                self.operation_type_id = suggested_op_type
            else:
                self.operation_type_id = False

    @api.onchange('first_name_en', 'last_name_en')
    def _onchange_names_to_username(self):
        if self.first_name_en and self.last_name_en:
            first_letter = self.first_name_en.strip()[0].lower()
            last_name = self.last_name_en.strip().replace(" ", "").lower()
            self.expected_username = f"{first_letter}.{last_name}"
        else:
            self.expected_username = False

    @api.depends('expected_username')
    def _compute_username_availability(self):
        for rec in self:
            if rec.expected_username:
                existing_user = self.env['res.users'].sudo().search([
                    ('login', '=', rec.expected_username)
                ], limit=1)

                if existing_user:
                    rec.username_available = False
                    suggestions = rec._generate_username_suggestions(rec.expected_username)
                    suggestions_text = ", ".join([f"'{s}'" for s in suggestions[:5]])
                    rec.username_warning = _(
                        "⚠ This username is already taken. Try one of these: %s"
                    ) % suggestions_text
                else:
                    rec.username_available = True
                    rec.username_warning = False
            else:
                rec.username_available = True
                rec.username_warning = False

    def _generate_username_suggestions(self, base_username):
        suggestions = []

        if '.' in base_username:
            parts = base_username.split('.', 1)
            first_letter = parts[0]
            last_name = parts[1]
        else:
            first_letter = base_username[0] if base_username else 'm'
            last_name = base_username[1:] if len(base_username) > 1 else 'name'

        for i in range(1, 20):
            suggestion = f"{first_letter}{i}.{last_name}"
            existing = self.env['res.users'].sudo().search([('login', '=', suggestion)], limit=1)
            if not existing:
                suggestions.append(suggestion)
                if len(suggestions) >= 5:
                    return suggestions

        for i in range(1, 20):
            suggestion = f"{first_letter}_{i}.{last_name}"
            existing = self.env['res.users'].sudo().search([('login', '=', suggestion)], limit=1)
            if not existing:
                suggestions.append(suggestion)
                if len(suggestions) >= 5:
                    return suggestions

        for i in range(1, 20):
            suggestion = f"{base_username}{i}"
            existing = self.env['res.users'].sudo().search([('login', '=', suggestion)], limit=1)
            if not existing:
                suggestions.append(suggestion)
                if len(suggestions) >= 5:
                    return suggestions

        return suggestions[:5]

    def action_open_wizard(self):
        self.ensure_one()

        if not self.expected_username:
            raise ValidationError(_("Please enter a username."))

        if not self.username_available:
            suggestions = self._generate_username_suggestions(self.expected_username)
            if suggestions:
                suggestions_list = "\n  • ".join(suggestions)
                error_msg = _(
                    "The username '%s' is already taken.\n\n"
                    "Please choose one of these available usernames:\n  • %s"
                ) % (self.expected_username, suggestions_list)
            else:
                error_msg = _("The username '%s' is already taken. Please choose another one.") % self.expected_username
            raise ValidationError(error_msg)

        if self.rep_type == 'presales' and not self.presales_location_id:
            raise ValidationError(
                _("Please specify the predefined warehouse location for the PreSales representative."))

        if not self.operation_type_id:
            raise ValidationError(_("Please select an Operation Type (PS-OUT or CV-OUT)."))

        return {
            'name': _('Confirm Sales Rep Creation'),
            'type': 'ir.actions.act_window',
            'res_model': 'sales.rep.confirm.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_onboarding_id': self.id}
        }


class SalesRepConfirmWizard(models.TransientModel):
    _name = 'sales.rep.confirm.wizard'
    _description = 'Confirm Sales Rep Creation Wizard'

    onboarding_id = fields.Many2one('sales.rep.onboarding', string="Request", required=True)


    def _get_next_sequence_number(self, env_sudo):
        """
        الحصول على الرقم التالي بناءً على أكبر رقم موجود فعلياً في قاعدة البيانات
        """
        all_profiles = env_sudo['sales.rep.profile'].search(
            [('sequence', '!=', False)],
            order='sequence desc',
            limit=100
        )

        if not all_profiles:
            return 1

        # استخراج جميع الأرقام الفعلية
        numbers = []
        for profile in all_profiles:
            match = re.search(r'(\d+)', profile.sequence)
            if match:
                numbers.append(int(match.group(1)))

        if not numbers:
            return 1

        # إرجاع أكبر رقم + 1
        return max(numbers) + 1


    def action_confirm(self):
        self.ensure_one()
        req = self.onboarding_id
        env_sudo = self.sudo().env

        auto_state_id = req.company_id.state_id.id

        auto_warehouse = env_sudo['stock.warehouse'].search([('company_id', '=', req.company_id.id)], limit=1)
        if req.rep_type == 'cashvan' and not auto_warehouse:
            raise ValidationError(
                _(f"No warehouse found for the company ({req.company_id.name}). Please check the warehouse settings.")
            )

        auto_branch_code = str(req.company_id.id).zfill(2)

        portal_group = env_sudo.ref('base.group_portal')
        industry = env_sudo['res.partner.industry'].search([('name', '=', 'زبائن جدد')], limit=1)

        if env_sudo['res.users'].search([('login', '=', req.expected_username)]):
            raise ValidationError(_(f"The username ({req.expected_username}) already exists in the system!"))

        user_vals = {
            'name': req.name_ar,
            'login': req.expected_username,
            'email': req.expected_username,
            'password': '123',
            'groups_id': [(6, 0, [portal_group.id])],
            'company_id': req.company_id.id,
            'company_ids': [(6, 0, [req.company_id.id])],
        }
        new_user = env_sudo['res.users'].create(user_vals)

        new_user.partner_id.write({
            'function': 'CashVan' if req.rep_type == 'cashvan' else 'PreSales',
            'state_id': auto_state_id,
            'industry_id': industry.id if industry else False,
        })

        location_id = False
        if req.rep_type == 'cashvan':
            parent_location = env_sudo['stock.location'].search([
                ('name', '=', 'CARS'),
                ('location_id', '=', auto_warehouse.view_location_id.id)
            ], limit=1)

            location_id = env_sudo['stock.location'].create({
                'name': req.name_ar,
                'location_id': parent_location.id if parent_location else auto_warehouse.view_location_id.id,
                'usage': 'internal',
                'company_id': req.company_id.id,
            }).id
        else:
            location_id = req.presales_location_id.id

        # ✅ الحصول على الرقم التالي
        next_number = self._get_next_sequence_number(env_sudo)

        # ✅ تنسيق الرقم بـ 3 خانات (zfill)
        rep_code = f"S{str(next_number).zfill(3)}"

        # ✅ التحقق من عدم وجود تكرار
        max_attempts = 50
        for attempt in range(max_attempts):
            existing_profile = env_sudo['sales.rep.profile'].with_context(active_test=False).search([
                ('sequence', '=', rep_code)
            ], limit=1)

            if not existing_profile:
                break

            next_number += 1
            rep_code = f"S{str(next_number).zfill(3)}"  # ✅ هنا كمان

            if attempt == max_attempts - 1:
                raise ValidationError(
                    _("Unable to generate a unique sequence after %d attempts. Please contact the system administrator.") % max_attempts
                )

        profile = env_sudo['sales.rep.profile'].create({
            'user_id': new_user.id,
            'company_id': req.company_id.id,
            'sales_team_type': req.rep_type,
            'location_id': location_id,
            'allow_usd_payment': req.allow_usd_payment,
            'allow_manual_offer': req.allow_manual_offer,
            'attachment_mandatory': req.attachment_mandatory,
            'allowed_distance_m': req.allowed_distance_m,
            'operation_type_id': req.operation_type_id.id,
            'sequence': rep_code,
        })

        cur_syp = env_sudo['res.currency'].search([('name', 'in', ['SYP', 'S.P'])], limit=1)
        cur_spo = env_sudo['res.currency'].search([('name', '=', 'SPO')], limit=1)
        cur_usd = env_sudo['res.currency'].search([('name', '=', 'USD')], limit=1)

        # ✅ استخدام رقم الترتيب مع 3 خانات
        number_part = str(next_number).zfill(3)

        currencies_setup = [
            {'cur': cur_syp, 'code': '1', 'name_suffix': '', 'short_code': f'S{number_part}'},
            {'cur': cur_spo, 'code': '2', 'name_suffix': ' SPO', 'short_code': f'OS{number_part}'},
            {'cur': cur_usd, 'code': '3', 'name_suffix': ' USD', 'short_code': f'$S{number_part}'},
        ]

        company_currency_id = req.company_id.currency_id.id

        for setup in currencies_setup:
            if not setup['cur']:
                continue

            target_currency_id = setup['cur'].id
            is_base_currency = (target_currency_id == company_currency_id)
            journal_currency_id = False if is_base_currency else target_currency_id

            acc_code = f"131{auto_branch_code}{setup['code']}{rep_code}"

            existing_acc = env_sudo['account.account'].search(
                [('code', '=', acc_code), ('company_ids', 'in', req.company_id.id)], limit=1)

            if not existing_acc:
                account = env_sudo['account.account'].create({
                    'code': acc_code,
                    'name': f"{req.name_ar}{setup['name_suffix']}",
                    'account_type': 'asset_cash',
                    'company_ids': [(6, 0, [req.company_id.id])],
                    'currency_id': journal_currency_id,
                })
            else:
                account = existing_acc

            journal_code = setup['short_code']

            counter = 1
            while env_sudo['account.journal'].search([
                ('code', '=', journal_code),
                ('company_id', '=', req.company_id.id)
            ], limit=1):
                journal_code = f"{setup['short_code']}-{counter}"
                counter += 1

            journal = env_sudo['account.journal'].create({
                'name': f"{req.name_ar}{setup['name_suffix']}",
                'type': 'cash',
                'company_id': req.company_id.id,
                'code': journal_code,
                'currency_id': journal_currency_id,
                'default_account_id': account.id,
            })

            if journal.inbound_payment_method_line_ids:
                journal.inbound_payment_method_line_ids.write({
                    'payment_account_id': account.id
                })

            if journal.outbound_payment_method_line_ids:
                journal.outbound_payment_method_line_ids.write({
                    'payment_account_id': account.id
                })

            env_sudo['sales.rep.cash.journal.map'].create({
                'profile_id': profile.id,
                'journal_id': journal.id,
            })

        req.write({'state': 'done'})

        return {
            'type': 'ir.actions.act_window',
            'res_model': 'sales.rep.profile',
            'res_id': profile.id,
            'view_mode': 'form',
            'target': 'current',
        }
