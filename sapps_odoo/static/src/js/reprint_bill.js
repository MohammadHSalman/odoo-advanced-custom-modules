/** @odoo-module */
import { PrintBillButton } from "@pos_restaurant/app/control_buttons/print_bill_button/print_bill_button";
import { patch } from "@web/core/utils/patch";
import { OrderReceipt } from "@point_of_sale/app/screens/receipt_screen/receipt/order_receipt";

patch(PrintBillButton.prototype, {
    async click() {

        const order = this.pos.get_order();

        // زيادة عدد النسخ
        order.reprint_count = (order.reprint_count || 0) + 1;

        // تصدير بيانات الطلب مع تضمين reprint_count
        const printData = {
            ...order.export_for_printing(), reprint_count: order.reprint_count // تمرير عدد النسخ إلى بيانات الطابعة
        };


        // طباعة الإيصال
        const printResult = await this.printer.print(OrderReceipt, {
            data: printData, formatCurrency: this.env.utils.formatCurrency,
        });

        if (!printResult) {
            this.pos.showTempScreen("BillScreen");
        }

    }
});
