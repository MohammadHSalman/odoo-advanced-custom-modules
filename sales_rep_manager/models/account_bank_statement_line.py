# -*- coding: utf-8 -*-
from odoo import api, Command, fields, models, _
from odoo.exceptions import UserError

class AccountBankStatementLine(models.Model):
    _inherit = 'account.bank.statement.line'

    # -------------------------------------------------------------------------
    # COMPUTE METHODS OVERRIDE
    # -------------------------------------------------------------------------

    # --- ?????: ?? ??? ??? ?????? ?????? ?? ??? ???? ---
    @api.depends('journal_id', 'currency_id', 'amount', 'foreign_currency_id', 'amount_currency',
                 'move_id.checked', 'move_id.line_ids.account_id', 'move_id.line_ids.amount_currency',
                 'move_id.line_ids.amount_residual_currency', 'move_id.line_ids.currency_id',
                 'move_id.line_ids.matched_debit_ids', 'move_id.line_ids.matched_credit_ids')
    def _compute_is_reconciled(self):
        for st_line in self:
            _liquidity_lines, suspense_lines, _other_lines = st_line._seek_for_lines()
            if not st_line.checked:
                st_line.amount_residual = -st_line.amount_currency if st_line.foreign_currency_id else -st_line.amount
            elif suspense_lines and suspense_lines[0].account_id.reconcile:
                st_line.amount_residual = sum(suspense_lines.mapped('amount_residual_currency'))
            elif suspense_lines:
                st_line.amount_residual = sum(suspense_lines.mapped('amount_currency'))
            else:
                 st_line.amount_residual = 0.0
            if not st_line.id:
                st_line.is_reconciled = False
            elif suspense_lines:
                suspense_currency = suspense_lines[0].currency_id
                st_line.is_reconciled = suspense_currency.is_zero(st_line.amount_residual)
            elif st_line.currency_id.is_zero(st_line.amount):
                st_line.is_reconciled = True
            else:
                st_line.is_reconciled = True

    # -------------------------------------------------------------------------
    # HELPERS OVERRIDE
    # -------------------------------------------------------------------------
    
    # --- ?????: ?? ????? ??? ?????? ????? ??? Singleton ???????? ?? ???? ?????? ---
    def _get_accounting_amounts_and_currencies(self):
        self.ensure_one()
        liquidity_lines, suspense_lines, other_lines = self._seek_for_lines()
        if suspense_lines and not other_lines:
            transaction_amount = -sum(suspense_lines.mapped('amount_currency'))
            transaction_currency = suspense_lines[0].currency_id
        else:
            transaction_amount = self.amount_currency if self.foreign_currency_id else self.amount
            transaction_currency = self.foreign_currency_id or (liquidity_lines and liquidity_lines[0].currency_id) or self.currency_id
        journal_amount = sum(liquidity_lines.mapped('amount_currency'))
        journal_currency = (liquidity_lines and liquidity_lines[0].currency_id) or self.currency_id
        company_amount = sum(liquidity_lines.mapped('balance'))
        company_currency = (liquidity_lines and liquidity_lines[0].company_currency_id) or self.company_id.currency_id
        return (transaction_amount, transaction_currency, journal_amount, journal_currency, company_amount, company_currency)

    # -------------------------------------------------------------------------
    # SYNCHRONIZATION OVERRIDE
    # -------------------------------------------------------------------------
    
    # --- ?????: ?? ??? ???? ???????? ?????? ?? ??? ???? ---
    def _synchronize_from_moves(self, changed_fields):
        if self._context.get('skip_account_move_synchronization'):
            return
        for st_line in self.with_context(skip_account_move_synchronization=True):
            move = st_line.move_id
            move_vals_to_write = {}
            st_line_vals_to_write = {}
            if 'line_ids' in changed_fields:
                liquidity_lines, suspense_lines, other_lines = st_line._seek_for_lines()
                company_currency = st_line.journal_id.company_id.currency_id
                journal_currency = st_line.journal_id.currency_id if st_line.journal_id.currency_id != company_currency else False
                if liquidity_lines:
                    first_liquidity_line = liquidity_lines[0]
                    st_line_vals_to_write.update({
                        'payment_ref': first_liquidity_line.name,
                        'partner_id': first_liquidity_line.partner_id.id,
                    })
                    if journal_currency:
                        st_line_vals_to_write['amount'] = sum(liquidity_lines.mapped('amount_currency'))
                    else:
                        st_line_vals_to_write['amount'] = sum(liquidity_lines.mapped('balance'))
                    move_vals_to_write['partner_id'] = first_liquidity_line.partner_id.id
                if suspense_lines:
                    suspense_currency = suspense_lines[0].currency_id
                    if journal_currency and suspense_currency == journal_currency:
                        st_line_vals_to_write.update({'amount_currency': 0.0, 'foreign_currency_id': False})
                    elif not journal_currency and suspense_currency == company_currency:
                        st_line_vals_to_write.update({'amount_currency': 0.0, 'foreign_currency_id': False})
                    elif not other_lines:
                        st_line_vals_to_write.update({
                            'amount_currency': -sum(suspense_lines.mapped('amount_currency')),
                            'foreign_currency_id': suspense_currency.id,
                        })
                move_vals_to_write['currency_id'] = (st_line.foreign_currency_id or journal_currency or company_currency).id
            if move_vals_to_write:
                move.with_context(skip_readonly_check=True).write(move._cleanup_write_orm_values(move, move_vals_to_write))
            if st_line_vals_to_write:
                st_line.write(move._cleanup_write_orm_values(st_line, st_line_vals_to_write))

    # --- ?????: ?? ??? ???? ???????? ??????? ???? ??? ---
    def _synchronize_to_moves(self, changed_fields):
        if self._context.get('skip_account_move_synchronization'):
            return
        if not any(field_name in changed_fields for field_name in ('payment_ref', 'amount', 'amount_currency', 'foreign_currency_id', 'currency_id', 'partner_id')):
            return
        for st_line in self.with_context(skip_account_move_synchronization=True):
            liquidity_lines, suspense_lines, _other_lines = st_line._seek_for_lines()
            journal = st_line.journal_id
            company_currency = journal.company_id.sudo().currency_id
            journal_currency = journal.currency_id if journal.currency_id != company_currency else False
            lines_to_remove = liquidity_lines + suspense_lines
            line_ids_commands = [Command.delete(line_id) for line_id in lines_to_remove.ids]
            new_line_vals = st_line._prepare_move_line_default_vals()
            line_ids_commands.append(Command.create(new_line_vals[0]))
            line_ids_commands.append(Command.create(new_line_vals[1]))
            st_line_vals = {
                'currency_id': (st_line.foreign_currency_id or journal_currency or company_currency).id,
                'line_ids': line_ids_commands,
            }
            if st_line.move_id.journal_id != journal:
                st_line_vals['journal_id'] = journal.id
            if st_line.move_id.partner_id != st_line.partner_id:
                st_line_vals['partner_id'] = st_line.partner_id.id
            st_line.move_id.with_context(skip_readonly_check=True).write(st_line_vals)

# --- ????? ????? ?? ?????? stock_accountant ---
# ??? ?????? ??? ?? ??? ??????? ????? ?????? ???? ?? ?????? ??? ??? ??? ???? ????
class StockAccountantBankStatementLine(models.Model):
    _inherit = 'account.bank.statement.line'

    # ??? ?????? ???? ?????? ?? stock_accountant ?????? ???? ??? ?? ??????? ?????
    # ??? ???? ??????? ??? ???? ?? ?????? ??????
    def _get_default_amls_matching_domain(self):
        # ??????? ?????? ??????? ??????? ?? account.bank.statement.line
        domain = super(StockAccountantBankStatementLine, self)._get_default_amls_matching_domain()
        
        # ??? ??? ????? ??? ?????? ???? ??? ??????? ?? ???? ?????? stock_accountant
        # ??? ?????? ?? ???? ???? ??? ????? ????????
        # ????: domain.append(('is_stock_related', '=', True))
        # ????? ??? ????? ?????? ??? ?????? ????? ?????? ??? ?? ????
        # ??? ?? ?????? ???? ?????? ?? ??? stock_accountant ?????? ???? ???
        return domain