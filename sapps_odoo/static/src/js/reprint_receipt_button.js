/** @odoo-module */

import { ReprintReceiptButton } from "@point_of_sale/app/screens/ticket_screen/reprint_receipt_button/reprint_receipt_button";
import { OrderReceipt } from "@point_of_sale/app/screens/receipt_screen/receipt/order_receipt";
import { patch } from "@web/core/utils/patch";

patch(ReprintReceiptButton.prototype, {
    async click() {
        if (!this.props.order) {
            return;
        }

        // زيادة عدد النسخ
        this.props.order.reprint_count = (this.props.order.reprint_count || 0) + 1;

        // تأكد من تضمين reprint_count في بيانات الطباعة
        const printData = {
            ...this.props.order.export_for_printing(),
            reprint_count: this.props.order.reprint_count // تمرير عدد النسخ إلى بيانات الطابعة
        };


        // طباعة الإيصال
        const printResult = await this.printer.print(OrderReceipt, {
            data: printData,
            formatCurrency: this.env.utils.formatCurrency,
        });

        // إظهار شاشة إعادة الطباعة إذا لم تتم الطباعة
        if (!printResult) {
            this.pos.showScreen("ReprintReceiptScreen", { order: this.props.order });
        }

    }
});
