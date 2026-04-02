# -*- coding: utf-8 -*-

from odoo import models, _
import math
from collections import defaultdict

from odoo.exceptions import UserError
from odoo.tools import float_is_zero


class PosSession(models.Model):
    _inherit = 'pos.session'
    def _prepare_line(self, order_line):
        """ Derive from order_line the order date, income account, amount and taxes information.

        These information will be used in accumulating the amounts for sales and tax lines.
        """

        def get_income_account(order_line):
            product = order_line.product_id
            income_account = product.with_company(order_line.company_id)._get_product_accounts()[
                                 'income'] or self.config_id.journal_id.default_account_id
            if not income_account:
                raise UserError(_('Please define income account for this product: "%s" (id:%d).',
                                  product.name, product.id))
            return order_line.order_id.fiscal_position_id.map_account(income_account)

        # الحصول على المنتج من order_line
        product = order_line.product_id

        # تحقق إذا كان المنتج خصمًا باستخدام display_name أو أي طريقة مناسبة
        is_discount = product.name.strip().lower() == 'discount'  # تأكد من أنك تستخدم القيمة الصحيحة للخصم
        print(product.name,'****')
        company_domain = self.env['account.tax']._check_company_domain(order_line.order_id.company_id)
        tax_ids = order_line.tax_ids_after_fiscal_position.filtered_domain(company_domain)
        sign = -1 if order_line.qty >= 0 else 1
        price = sign * order_line.price_unit

        # إذا كان المنتج خصمًا، تجاهل الضرائب
        if is_discount:
            # لا يتم حساب الضرائب للخصم
            tax_data = {'taxes': [], 'base_tags': []}
        else:
            # إذا لم يكن خصمًا، حساب الضرائب بناءً على السعر الأساسي
            check_refund = lambda x: x.qty * x.price_unit < 0
            is_refund = check_refund(order_line)
            tax_data = tax_ids.compute_all(price_unit=price, quantity=abs(order_line.qty), currency=self.currency_id,
                                           is_refund=is_refund, fixed_multiplicator=sign)

            print(price,'price')
            print(abs(order_line.qty),'abs(order_line.qty)')
            print(tax_data,'tax_data')

        taxes = tax_data['taxes']
        for tax in taxes:
            tax_rep = self.env['account.tax.repartition.line'].browse(tax['tax_repartition_line_id'])
            tax['account_id'] = tax_rep.account_id.id
        date_order = order_line.order_id.date_order
        taxes = [{'date_order': date_order, **tax} for tax in taxes]

        return {
            'date_order': order_line.order_id.date_order,
            'income_account_id': get_income_account(order_line).id,
            'amount': order_line.price_subtotal,
            'taxes': taxes,  # يجب أن يكون خاليًا إذا كان خصمًا
            'base_tags': tuple(tax_data['base_tags']),
        }
    def _accumulate_amounts(self, data):
        # Helper function to round amounts based on the currency
        def round_amount_based_on_currency(amount):
            if self.currency_id.id == 'base.SYP':
                return math.ceil(abs(amount) / 100) * 100 * (-1 if amount < 0 else 1)
            else:
                return math.ceil(abs(amount)) * (-1 if amount < 0 else 1)

        # Call the superclass method to get base data
        data = super()._accumulate_amounts(data)

        amounts = lambda: {'amount': 0.0, 'amount_converted': 0.0}
        tax_amounts = lambda: {'amount': 0.0, 'amount_converted': 0.0, 'base_amount': 0.0, 'base_amount_converted': 0.0}
        split_receivables_bank = defaultdict(amounts)
        split_receivables_cash = defaultdict(amounts)
        split_receivables_pay_later = defaultdict(amounts)
        combine_receivables_bank = defaultdict(amounts)
        combine_receivables_cash = defaultdict(amounts)
        combine_receivables_pay_later = defaultdict(amounts)
        combine_invoice_receivables = defaultdict(amounts)
        split_invoice_receivables = defaultdict(amounts)
        sales = defaultdict(amounts)
        taxes = defaultdict(tax_amounts)
        stock_expense = defaultdict(amounts)
        stock_return = defaultdict(amounts)
        stock_output = defaultdict(amounts)
        rounding_difference = {'amount': 0.0, 'amount_converted': 0.0}
        combine_inv_payment_receivable_lines = defaultdict(lambda: self.env['account.move.line'])
        split_inv_payment_receivable_lines = defaultdict(lambda: self.env['account.move.line'])
        rounded_globally = self.company_id.tax_calculation_rounding_method == 'round_globally'
        pos_receivable_account = self.company_id.account_default_pos_receivable_account_id
        currency_rounding = self.currency_id.rounding
        closed_orders = self._get_closed_orders()

        for order in closed_orders:
            order_is_invoiced = order.is_invoiced
            for payment in order.payment_ids:
                amount = payment.amount
                if float_is_zero(amount, precision_rounding=currency_rounding):
                    continue
                date = payment.payment_date
                payment_method = payment.payment_method_id
                is_split_payment = payment.payment_method_id.split_transactions
                payment_type = payment_method.type

                if payment_type != 'pay_later':
                    if is_split_payment and payment_type == 'cash':
                        split_receivables_cash[payment] = self._update_amounts(
                            split_receivables_cash[payment],
                            {'amount': amount},
                            date
                        )
                    elif not is_split_payment and payment_type == 'cash':
                        combine_receivables_cash[payment_method] = self._update_amounts(
                            combine_receivables_cash[payment_method],
                            {'amount': amount},
                            date
                        )
                    elif is_split_payment and payment_type == 'bank':
                        split_receivables_bank[payment] = self._update_amounts(
                            split_receivables_bank[payment],
                            {'amount': amount},
                            date
                        )
                    elif not is_split_payment and payment_type == 'bank':
                        combine_receivables_bank[payment_method] = self._update_amounts(
                            combine_receivables_bank[payment_method],
                            {'amount': amount},
                            date
                        )

                    if order_is_invoiced:
                        if is_split_payment:
                            split_inv_payment_receivable_lines[payment] |= payment.account_move_id.line_ids.filtered(
                                lambda line: line.account_id == pos_receivable_account
                            )
                            split_invoice_receivables[payment] = self._update_amounts(
                                split_invoice_receivables[payment],
                                {'amount': payment.amount},
                                order.date_order
                            )
                        else:
                            combine_inv_payment_receivable_lines[
                                payment_method] |= payment.account_move_id.line_ids.filtered(
                                lambda line: line.account_id == pos_receivable_account
                            )
                            combine_invoice_receivables[payment_method] = self._update_amounts(
                                combine_invoice_receivables[payment_method],
                                {'amount': payment.amount},
                                order.date_order
                            )

                    if payment_type == 'pay_later' and not order_is_invoiced:
                        if is_split_payment:
                            split_receivables_pay_later[payment] = self._update_amounts(
                                split_receivables_pay_later[payment],
                                {'amount': amount},
                                date
                            )
                        elif not is_split_payment:
                            combine_receivables_pay_later[payment_method] = self._update_amounts(
                                combine_receivables_pay_later[payment_method],
                                {'amount': amount},
                                date
                            )

            if not order_is_invoiced:
                order_taxes = defaultdict(tax_amounts)
                for order_line in order.lines:
                    line = self._prepare_line(order_line)
                    sale_key = (
                        line['income_account_id'],
                        -1 if line['amount'] < 0 else 1,
                        tuple((tax['id'], tax['account_id'], tax['tax_repartition_line_id']) for tax in line['taxes']),
                        line['base_tags'],
                    )
                    sales[sale_key] = self._update_amounts(
                        sales[sale_key],
                        {'amount': line['amount']},
                        line['date_order'],
                        round=False
                    )
                    sales[sale_key].setdefault('tax_amount', 0.0)
                    for tax in line['taxes']:
                        tax_key = (
                            tax['account_id'] or line['income_account_id'],
                            tax['tax_repartition_line_id'],
                            tax['id'],
                            tuple(tax['tag_ids'])
                        )
                        # Apply rounding to tax amount
                        rounded_tax_amount = round_amount_based_on_currency(tax['amount'])
                        sales[sale_key]['tax_amount'] += rounded_tax_amount
                        order_taxes[tax_key] = self._update_amounts(
                            order_taxes[tax_key],
                            {'amount': rounded_tax_amount, 'base_amount': tax['base']},
                            tax['date_order'],
                            round=not rounded_globally
                        )
                for tax_key, amounts in order_taxes.items():
                    if rounded_globally:
                        amounts = self._round_amounts(amounts)
                    for amount_key, amount in amounts.items():
                        taxes[tax_key][amount_key] += amount

                if self.company_id.anglo_saxon_accounting and order.picking_ids.ids:
                    stock_moves = self.env['stock.move'].sudo().search([
                        ('picking_id', 'in', order.picking_ids.ids),
                        ('company_id.anglo_saxon_accounting', '=', True),
                        ('product_id.categ_id.property_valuation', '=', 'real_time')
                    ])
                    for move in stock_moves:
                        exp_key = move.product_id._get_product_accounts()['expense']
                        out_key = move.product_id.categ_id.property_stock_account_output_categ_id
                        signed_product_qty = move.product_qty
                        if move._is_in():
                            signed_product_qty *= -1
                        amount = signed_product_qty * move.product_id._compute_average_price(0, move.quantity, move)
                        stock_expense[exp_key] = self._update_amounts(
                            stock_expense[exp_key],
                            {'amount': amount},
                            move.picking_id.date,
                            force_company_currency=True
                        )
                        if move._is_in():
                            stock_return[out_key] = self._update_amounts(
                                stock_return[out_key],
                                {'amount': amount},
                                move.picking_id.date,
                                force_company_currency=True
                            )
                        else:
                            stock_output[out_key] = self._update_amounts(
                                stock_output[out_key],
                                {'amount': amount},
                                move.picking_id.date,
                                force_company_currency=True
                            )

                if self.config_id.cash_rounding:
                    diff = order.amount_paid - order.amount_total
                    rounding_difference = self._update_amounts(rounding_difference, {'amount': diff}, order.date_order)

                partners = (order.partner_id | order.partner_id.commercial_partner_id)
                partners._increase_rank('customer_rank')

        if self.company_id.anglo_saxon_accounting:
            global_session_pickings = self.picking_ids.filtered(lambda p: not p.pos_order_id)
            if global_session_pickings:
                stock_moves = self.env['stock.move'].sudo().search([
                    ('picking_id', 'in', global_session_pickings.ids),
                    ('company_id.anglo_saxon_accounting', '=', True),
                    ('product_id.categ_id.property_valuation', '=', 'real_time'),
                ])
                for move in stock_moves:
                    exp_key = move.product_id._get_product_accounts()['expense']
                    out_key = move.product_id.categ_id.property_stock_account_output_categ_id
                    signed_product_qty = move.product_qty
                    if move._is_in():
                        signed_product_qty *= -1
                    amount = signed_product_qty * move.product_id._compute_average_price(0, move.quantity, move)
                    stock_expense[exp_key] = self._update_amounts(
                        stock_expense[exp_key],
                        {'amount': amount},
                        move.picking_id.date,
                        force_company_currency=True
                    )
                    if move._is_in():
                        stock_return[out_key] = self._update_amounts(
                            stock_return[out_key],
                            {'amount': amount},
                            move.picking_id.date,
                            force_company_currency=True
                        )
                    else:
                        stock_output[out_key] = self._update_amounts(
                            stock_output[out_key],
                            {'amount': amount},
                            move.picking_id.date,
                            force_company_currency=True
                        )

        MoveLine = self.env['account.move.line'].with_context(check_move_validity=False, skip_invoice_sync=True)
        print(taxes, '++++++++++++++++++++++++')
        data.update({
            'taxes': taxes,
            'sales': sales,
            'stock_expense': stock_expense,
            'split_receivables_bank': split_receivables_bank,
            'combine_receivables_bank': combine_receivables_bank,
            'split_receivables_cash': split_receivables_cash,
            'combine_receivables_cash': combine_receivables_cash,
            'combine_invoice_receivables': combine_invoice_receivables,
            'split_receivables_pay_later': split_receivables_pay_later,
            'combine_receivables_pay_later': combine_receivables_pay_later,
            'stock_return': stock_return,
            'stock_output': stock_output,
            'combine_inv_payment_receivable_lines': combine_inv_payment_receivable_lines,
            'rounding_difference': rounding_difference,
            'MoveLine': MoveLine,
            'split_invoice_receivables': split_invoice_receivables,
            'split_inv_payment_receivable_lines': split_inv_payment_receivable_lines,
        })
        return data
