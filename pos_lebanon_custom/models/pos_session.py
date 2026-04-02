from odoo import models, api, fields

class PosSession(models.Model):
    _inherit = 'pos.session'

    def get_sale_details(self, session_ids=None):
        res = super().get_sale_details(session_ids)

        if session_ids:
            sessions = self.browse(session_ids)
        else:
            sessions = self

        orders = self.env['pos.order'].search([('session_id', 'in', sessions.ids)])

        orders_details = []
        currency_totals = {}

        for order in orders:
            payment_list = []
            order_pos_currency = order.currency_id

            for payment in order.payment_ids:
                journal = payment.payment_method_id.journal_id
                pay_currency = journal.currency_id or journal.company_id.currency_id

                amount_in_pos_ccy = payment.amount

                display_amount = amount_in_pos_ccy
                display_currency_name = pay_currency.name

                # Calculate the physical amount collected
                if pay_currency != order_pos_currency:
                    if order_pos_currency.rate > 0:
                        display_amount = (amount_in_pos_ccy / order_pos_currency.rate) * pay_currency.rate

                payment_list.append({
                    'method': payment.payment_method_id.name,
                    'currency': display_currency_name,
                    'amount': display_amount
                })

                key = display_currency_name
                if key not in currency_totals:
                    currency_totals[key] = 0.0
                currency_totals[key] += display_amount

            orders_details.append({
                'name': order.name,
                'total': order.amount_total,
                'payments': payment_list
            })

        res['orders_breakdown'] = orders_details
        res['currency_grand_totals'] = currency_totals
        return res
