/** @odoo-module **/
/* global Sha1 */

import {_t} from "@web/core/l10n/translation";
import {ProductScreen} from "@point_of_sale/app/screens/product_screen/product_screen";
import {patch} from "@web/core/utils/patch";
import {TextAreaPopup} from "@point_of_sale/app/utils/input_popups/textarea_popup";
import {NumberPopup} from "@point_of_sale/app/utils/input_popups/number_popup";
import {ErrorPopup} from "@point_of_sale/app/errors/popups/error_popup";
import {useService} from "@web/core/utils/hooks";
import {SelectionPopup} from "@point_of_sale/app/utils/input_popups/selection_popup";

// Helper function to check permissions and display error popups
async function checkPermission(hasPermission, title, body) {
    if (!hasPermission) {
        await this.popup.add(ErrorPopup, {title, body});
        return false;
    }
    return true;
}

// Helper function to handle input popups
async function handlePopupInput(popupType, title) {
    const {confirmed, payload: inputNote} = await this.popup.add(popupType, {title});
    if (!inputNote) {
        await this.popup.add(ErrorPopup, {title: _t("Alert"), body: _t("Reason is required!")});
        return {confirmed: false};
    }
    return {confirmed, inputNote};
}

// Patch the ProductScreen class
patch(ProductScreen.prototype, {
    setup() {
        super.setup(...arguments);
        this.popup = useService("popup");
    },

    async onNumpadClick(buttonValue) {
        const {pos, popup, currentOrder} = this;

        // Handle discount and price permissions
        if (buttonValue === 'discount' && !await checkPermission.call(this, pos.cashier.enable_emp_discount, _t("Discount Not Allowed"), _t("You are not authorized to apply discounts."))) {
            return false;
        }

        if (buttonValue === 'price' && !await checkPermission.call(this, pos.cashier.enable_emp_price, _t("Price Change Not Allowed"), _t("You are not authorized to change prices."))) {
            return false;
        }

        // Handle special cases for discount and price
        if (["quantity", "discount", "price"].includes(buttonValue)) {
            if (buttonValue === 'discount') {
                const {confirmed, inputNote} = await handlePopupInput.call(this, TextAreaPopup, _t("Please input Discount Reason"));

                if (confirmed) {
                    currentOrder.selected_orderline.discount_line_reason = inputNote;

                    // Show discount type selection popup
                    const {confirmed: typeConfirmed, payload: discountType} = await this.popup.add(SelectionPopup, {
                        title: _t("Select Discount Type"),
                        list: [
                            {id: "0", label: _t("Percentage"), item: "percentage"},
                            {id: "1", label: _t("Fixed Amount"), item: "fixed"}
                        ]
                    });

                    if (typeConfirmed) {
                        const {confirmed: valueConfirmed, payload: discountValue} = await this.popup.add(NumberPopup, {
                            title: discountType === 'percentage' ? _t("Enter Discount Percentage") : _t("Enter Fixed Discount Amount"),
                            startingValue: 0,
                            isInputSelected: true,
                        });

                        if (valueConfirmed) {
                            const discount = parseFloat(discountValue);
                            if (discountType === 'percentage') {
                                currentOrder.selected_orderline.set_discount(discount);
                            } else if (discountType === 'fixed') {
                                // احصل على السعر الأصلي للمنتج
                                const price = currentOrder.selected_orderline.get_display_price();

                                // قيمة الخصم الثابتة
                                const fixedDiscount = parseFloat(discount);

                                // احسب النسبة المئوية للخصم
                                const discountPercentage = (fixedDiscount / price) * 100;

                                // ضبط الخصم كنسبة مئوية
                                currentOrder.selected_orderline.set_discount(discountPercentage.toFixed(2));
                            } else {
                                console.error('Unknown discount type:', discountType);
                            }
                        }
                    }
                }
            } else if (buttonValue === 'price') {
                const {confirmed, inputNote} = await handlePopupInput.call(this, TextAreaPopup, _t("Please input Price Reason"));

                if (confirmed) {
                    currentOrder.selected_orderline.discount_line_reason = inputNote;
                    this.numberBuffer.capture();
                    this.numberBuffer.reset();
                    this.pos.numpadMode = buttonValue;
                    return;
                }
            }

            this.numberBuffer.capture();
            this.numberBuffer.reset();
            this.pos.numpadMode = buttonValue;
            return;
        }

        this.numberBuffer.sendKey(buttonValue);
    },

    _setValue(val) {
        super._setValue(val);
        const mode = this.pos.numpadMode;
        const order = this.pos.get_order();

        if (order.get_selected_orderline() && mode === "discount") {
            const selectedLine = order.get_selected_orderline();
            selectedLine.set_discount(0);

            let sh_dic = parseFloat(selectedLine.get_global_discount()).toFixed(2);
            selectedLine.set_discount(sh_dic);

            const price = selectedLine.get_display_price();
            const currentPrice = (price * val) / 100;
            const discount = ((price * selectedLine.quantity - currentPrice) / (selectedLine.price * selectedLine.quantity)) * 100;
            selectedLine.set_discount(discount.toFixed(2));
        }
    }
});
