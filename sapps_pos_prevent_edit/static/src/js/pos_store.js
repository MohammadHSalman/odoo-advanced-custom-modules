/** @odoo-module */
import {patch} from "@web/core/utils/patch";
import {PosStore} from "@point_of_sale/app/store/pos_store";
import {ErrorPopup} from "@point_of_sale/app/errors/popups/error_popup";
import {_t} from "@web/core/l10n/translation";

patch(PosStore.prototype, {
    async setup(...args) {
        return await super.setup(...args);
    },

    async sendOrderInPreparation(order, cancelled = false) {
        if (this.printers_category_ids_set.size) {
            console.warn('**');
            try {
                const changes = order.changesToOrder(cancelled);

                if (changes.cancelled.length > 0 || changes.new.length > 0) {
                    const isPrintSuccessful = await order.printChanges(cancelled);
                    if (!isPrintSuccessful) {
                        this.popup.add(ErrorPopup, {
                            title: _t("Printing failed"),
                            body: _t("Failed to print the changes in the order."),
                        });
                    }
                }
            } catch (e) {
                console.warn("Failed to print the changes in the order", e);
            }
        }
    },

    async sendOrderInPreparationUpdateLastChange(order, cancelled = false) {
        // التحقق من وجود كميات سلبية في الفئات أو المنتجات
        let productName = ""; // متغير لتخزين اسم المنتج الذي يحتوي على الكمية السلبية
        const hasNegativeCount = order.get_orderlines().some(line => {
            // الخطوط تحتوي على معرفات فريدة كالمفاتيح، يمكننا الوصول إليها باستخدام Object.keys أو for...in
            for (let lineId in line.order.getOrderChanges().orderlines) {
                const orderLine = line.order.getOrderChanges().orderlines[lineId]; // هنا نقوم بالوصول إلى السطر باستخدام المعرف
                const quantity = orderLine.quantity; // الحصول على الكمية
                const name = orderLine.name; // الحصول على اسم المنتج
                console.warn(`Line ID: ${lineId}, Quantity: ${quantity}, Name:${name}`);

                // تخزين اسم المنتج إذا كانت الكمية سلبية
                if (quantity <= 0) {
                    productName = name; // حفظ اسم المنتج في المتغير
                    return true; // إذا كانت الكمية أقل من أو تساوي صفر، نعيد true لإيقاف العملية
                }
            }
            return false; // إذا لم نجد كمية سلبية
        });
        console.log(this.selectedOrder.pos.user.disable_cancellation,'----')
        if (hasNegativeCount && productName && this.selectedOrder.pos.user.disable_cancellation) {
            // إذا كانت الكميات تحتوي على قيمة سلبية، إظهار رسالة خطأ وإيقاف العملية
            this.popup.add(ErrorPopup, {
                title: _t("Invalid Quantity"),
                body: _t(`Cannot cancel the product (${productName}) as it is in preparation.`), // إضافة اسم المنتج هنا
            });
            return; // إيقاف العملية
        } else {
            await this.sendOrderInPreparation(order, cancelled);
            order.updateLastOrderChange();

            // تأكد من أن last_order_change يتم تحديثها في قاعدة البيانات
            order.save_to_db();
            order.pos.ordersToUpdateSet.add(order);
            await order.pos.sendDraftToServer();
        }
    }
    ,

    async submitOrder() {
        if (!this.clicked) {
            this.clicked = true;
            try {
                await this.pos.sendOrderInPreparationUpdateLastChange(this.currentOrder);
            } finally {
                this.clicked = false;
            }
        }
    },
});
