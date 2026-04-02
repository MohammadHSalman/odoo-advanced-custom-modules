/** @odoo-module */

import { PaymentScreenStatus } from "@point_of_sale/app/screens/payment_screen/payment_status/payment_status";
import { patch } from "@web/core/utils/patch";

patch(PaymentScreenStatus.prototype, {
    setup() {
        super.setup();
    },

    get secondaryCurrencyInfo() {
        const order = this.props.order;
        if (!order) return null;

        const pos = this.env.services.pos;
        if (!pos) return null;

        const due = order.get_due(); 
        if (due <= 0) return null;

        const posCurrency = pos.currency;

        let lbpCurrency = null;

        if (Array.isArray(pos.currencies)) {
            lbpCurrency = pos.currencies.find(c => c.name === 'LBP');
        }
        else if (pos.currencies && typeof pos.currencies === 'object') {
             lbpCurrency = Object.values(pos.currencies).find(c => c.name === 'LBP');
        }

        if (!lbpCurrency && pos.payment_methods) {
            const lbpMethod = pos.payment_methods.find(pm => {
                const cName = pm.currency_id ? pm.currency_id.name : (pm.journal_id && pm.journal_id.currency_id ? pm.journal_id.currency_id.name : '');
                return cName === 'LBP';
            });

            if (lbpMethod) {
                lbpCurrency = lbpMethod.currency_id || (lbpMethod.journal_id ? lbpMethod.journal_id.currency_id : null);
            }
        }

        if (!lbpCurrency || posCurrency.id === lbpCurrency.id) return null;

        if (!posCurrency.rate || !lbpCurrency.rate) return null;

        const amountInLbp = (due / posCurrency.rate) * lbpCurrency.rate;

        return {
            amount: this.env.utils.formatCurrency(amountInLbp, lbpCurrency.id),
            symbol: lbpCurrency.symbol,
            name: lbpCurrency.name
        };
    }
});
