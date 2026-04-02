# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import ValidationError


class AccountJournal(models.Model):
    _inherit = 'account.journal'

    def name_get(self):
        res = super().name_get()
        if self.env.context.get('show_currency_in_name'):
            new = []
            for rec_id, name in res:
                j = self.browse(rec_id)
                cur = j.currency_id or j.company_id.currency_id
                if cur:
                    name = f"{name} ({cur.name})"
                new.append((rec_id, name))
            return new
        return res


class SalesRepresentativeProfile(models.Model):
    _name = 'sales.rep.profile'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _description = 'Sales Representative Profile'

    sequence = fields.Char(
        string="Sequence",
        copy=False,
        tracking=True
    )

    allow_usd_payment = fields.Boolean(
        string='Allow usd payment',
        required=False)
    attachment_mandatory = fields.Boolean(
        string='Is the attachment mandatory?',
        default=False)
    operation_type_id = fields.Many2one('stock.picking.type', 'Operation Type', check_company=True, copy=False)

    user_id = fields.Many2one(
        'res.users',
        string='User',
        required=True,
        domain=lambda self: [('groups_id', 'in', self.env.ref('base.group_portal').id)],
        tracking=True,
        index=True,
    )
    name = fields.Char(
        string='Representative Name',
        compute='_compute_name',
        store=True,
        tracking=True,
    )

    location_id = fields.Many2one(
        'stock.location',
        string='Location for Representative',
        tracking=True,
    )
    sales_team_type = fields.Selection(
        [('cashvan', 'CashVan'), ('presales', 'PreSales')],
        string="Sales Team",
        required=True,
        default='cashvan',
        tracking=True,
    )

    company_id = fields.Many2one(
        'res.company',
        string='Company',
        required=True,
        default=lambda self: self.env.company,
        tracking=True,
    )
    route_id = fields.Many2one(
        'route.line',
        string="Route",
        help="Route",
        tracking=True,
    )

    # المصدر الحقيقي للربط (عملة فريدة لكل مندوب)
    journal_map_ids = fields.One2many(
        'sales.rep.cash.journal.map', 'profile_id',
        string="Cash Journal Mapping",
        help="One cash journal per currency for this representative."
    )

    # عرض كتاغز مع مزامنة كاملة مع الـ One2many
    journal_tag_ids = fields.Many2many(
        'account.journal',
        string='Cash Journals',
        compute='_compute_journal_tag_ids',
        inverse='_inverse_journal_tag_ids',
        store=False,
        help="Tag-style view; syncs with journal_map_ids."
    )

    # قائمة الجورنالات المتاحة فقط (تستثني المعيّنة لمندوب آخر)
    available_cash_journal_ids = fields.Many2many(
        'account.journal',
        string='Available Cash Journals',
        compute='_compute_available_cash_journal_ids',
        store=False,
        compute_sudo=True,
        help="Cash journals not assigned to any other sales representative in the same company."
    )
    allowed_distance_m = fields.Float(
        string="Allowed Distance (meters)",
        help="Maximum allowed distance in meters for this sales representative.",
        default=0.0,
        tracking=True
    )

    _sql_constraints = [
        ('uniq_user_profile', 'unique(user_id)',
         'Each user can have only one Sales Representative Profile.')
    ]

    # @api.model
    # def create(self, vals):
    #     if not vals.get('sequence'):
    #         vals['sequence'] = self.env['ir.sequence'].next_by_code('sales.rep.profile') or 'S0000'
    #     return super(SalesRepresentativeProfile, self).create(vals)
    #
    # @api.model
    # def init(self):
    #     # يتم استدعاؤها عند install/upgrade للموديول
    #     profiles = self.search([('sequence', '=', False)])
    #     seq = self.env['ir.sequence']
    #     for p in profiles:
    #         p.sequence = seq.next_by_code('sales.rep.profile') or 'S0000'
    @api.depends('user_id', 'sequence')
    def _compute_name(self):
        for rec in self:
            if rec.sequence:
                rec.name = f"{rec.sequence} - {rec.user_id.name}"
            else:
                rec.name = rec.user_id.name

    @api.constrains('user_id')
    def _check_single_profile_per_user(self):
        for rec in self:
            if not rec.user_id:
                continue
            dup_count = self.with_context(active_test=False).search_count([
                ('user_id', '=', rec.user_id.id),
                ('id', '!=', rec.id),
            ])
            if dup_count:
                raise ValidationError(
                    _("This user already has a Sales Representative Profile. Only one is allowed.")
                )

    def resolve_cash_journal(self, currency):
        """Return the mapped cash journal for the given currency (record of res.currency)."""
        self.ensure_one()
        if not currency:
            return False
        line = self.journal_map_ids.filtered(lambda l: l.currency_id.id == currency.id)[:1]
        return line.journal_id if line else False

    # التاغز ← حساب من المابات
    @api.depends('journal_map_ids.journal_id')
    def _compute_journal_tag_ids(self):
        for rec in self:
            rec.journal_tag_ids = rec.journal_map_ids.mapped('journal_id')

    # التاغز ← مزامنة عكسية للمابات (يدعم السجل غير المحفوظ)
    def _inverse_journal_tag_ids(self):
        for rec in self:
            desired_journals = rec.journal_tag_ids

            # إذا جديد: استخدم أوامر x2many مباشرة
            if not rec.id:
                wanted_by_currency = {}
                for j in desired_journals:
                    cur = j.currency_id or rec.company_id.currency_id
                    wanted_by_currency[cur.id if cur else False] = j
                commands = [(5, 0, 0)]
                for j in wanted_by_currency.values():
                    commands.append((0, 0, {'journal_id': j.id}))
                rec.update({'journal_map_ids': commands})
                continue

            current_journals = rec.journal_map_ids.mapped('journal_id')
            to_add = desired_journals - current_journals
            to_remove = current_journals - desired_journals

            if to_remove:
                rec.journal_map_ids.filtered(lambda l: l.journal_id in to_remove).unlink()

            for j in to_add:
                # منع اختيار جورنال مخصص لمندوب آخر بنفس الشركة
                other_line = self.env['sales.rep.cash.journal.map'].search([
                    ('journal_id', '=', j.id),
                    ('company_id', '=', rec.company_id.id),
                    ('profile_id', '!=', rec.id),
                ], limit=1)
                if other_line:
                    raise ValidationError(
                        _("The cash journal '%s' is already assigned to another representative.") % j.display_name
                    )

                expected_currency = j.currency_id or rec.company_id.currency_id
                conflict_line = rec.journal_map_ids.filtered(lambda l: l.currency_id == expected_currency)[:1]
                if conflict_line:
                    conflict_line.unlink()
                self.env['sales.rep.cash.journal.map'].create({
                    'profile_id': rec.id,
                    'journal_id': j.id,
                })

    # حساب الجورنالات المتاحة: نقدية + في نفس الشركة (أو بدون شركة) − المعينة لغيره
    def _compute_available_cash_journal_ids(self):
        Map = self.env['sales.rep.cash.journal.map'].sudo()
        Journal = self.env['account.journal'].sudo()
        for rec in self:
            # الجورنالات النقدية ضمن نفس الشركة أو بدون شركة
            base_domain = [('type', '=', 'cash'),
                           '|', ('company_id', '=', False), ('company_id', '=', rec.company_id.id)]
            # المعيّنة لغير هذا البروفايل
            other_maps = Map.search([
                ('company_id', '=', rec.company_id.id),
                ('profile_id', '!=', rec.id if rec.id else 0),
            ])
            excluded_ids = set(other_maps.mapped('journal_id').ids)
            domain = list(base_domain)
            if excluded_ids:
                domain.append(('id', 'not in', list(excluded_ids)))
            rec.available_cash_journal_ids = Journal.search(domain)

    @api.onchange('company_id')
    def _onchange_company_id(self):
        """Clear company-dependent fields when company changes."""
        self.location_id = False
        self.operation_type_id = False
        self.journal_map_ids = [(5, 0, 0)]


class SalesRepCashJournalMap(models.Model):
    _name = 'sales.rep.cash.journal.map'
    _description = 'Cash Journal per Sales Rep per Currency'
    _rec_name = 'journal_id'

    profile_id = fields.Many2one(
        'sales.rep.profile',
        required=True,
        ondelete='cascade',
        index=True
    )
    user_id = fields.Many2one(related='profile_id.user_id', store=True, readonly=True)
    company_id = fields.Many2one(related='profile_id.company_id', store=True, readonly=True)

    journal_id = fields.Many2one(
        'account.journal',
        string='Cash Journal',
        required=True,
        domain="[('type','=','cash'), '|', ('company_id','=',False), ('company_id','=',company_id)]",
        help="Cash journal to be used by this representative."
    )

    currency_id = fields.Many2one(
        'res.currency',
        string='Currency',
        compute='_compute_currency_id',
        store=True,
        readonly=True
    )

    _sql_constraints = [
        ('uniq_profile_currency', 'unique(profile_id, currency_id)',
         'A currency is already mapped to a cash journal for this representative.'),
        # يمنع تعيين نفس الجورنال لأكثر من مندوب داخل نفس الشركة
        ('uniq_company_journal', 'unique(company_id, journal_id)',
         'This cash journal is already assigned to another representative in this company.'),
    ]

    @api.model
    def create(self, vals):
        if not vals.get('profile_id'):
            ctx = self.env.context
            vals['profile_id'] = ctx.get('default_profile_id') or ctx.get('profile_id')
        return super().create(vals)

    @api.depends('journal_id', 'company_id')
    def _compute_currency_id(self):
        for rec in self:
            rec.currency_id = rec.journal_id.currency_id or (rec.company_id and rec.company_id.currency_id) or False

    @api.constrains('journal_id', 'company_id', 'currency_id')
    def _check_company_and_currency(self):
        for rec in self:
            if rec.journal_id.company_id and rec.journal_id.company_id != rec.company_id:
                raise ValidationError(_("Selected journal belongs to a different company."))
            expected = rec.journal_id.currency_id or (rec.company_id and rec.company_id.currency_id) or False
            if rec.currency_id != expected:
                raise ValidationError(
                    _("Currency must match the journal currency (or the company currency if journal has none)."))
