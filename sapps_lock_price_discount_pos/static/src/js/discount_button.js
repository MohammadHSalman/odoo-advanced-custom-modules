/** @odoo-module **/

import {_t} from "@web/core/l10n/translation";
import {ProductScreen} from "@point_of_sale/app/screens/product_screen/product_screen";
import {useService} from "@web/core/utils/hooks";
import {NumberPopup} from "@point_of_sale/app/utils/input_popups/number_popup";
import {ErrorPopup} from "@point_of_sale/app/errors/popups/error_popup";
import {TextAreaPopup} from "@point_of_sale/app/utils/input_popups/textarea_popup";
import {
    DiscountButton as OriginalDiscountButton
} from "@pos_discount/overrides/components/discount_button/discount_button";
import {usePos} from "@point_of_sale/app/store/pos_hook";
import {parseFloat} from "@web/views/fields/parsers";
import {SelectionPopup} from "@point_of_sale/app/utils/input_popups/selection_popup";

class DiscountButton extends OriginalDiscountButton {
    static template = "pos_discount.DiscountButton";

    setup() {
        this.pos = usePos();
        this.popup = useService("popup");
    }

    // async click() {
    //     var self = this;
    //
    //     // التحقق من تمكين الخصم العالمي للموظف الحالي
    //     if (this.pos.cashier.enable_emp_global_discount) {
    //         // إذا كان الخصم العالمي ممكناً، يطلب إدخال سبب الخصم
    //         const {confirmed, payload: inputNote} = await this.popup.add(TextAreaPopup, {
    //             title: _t("Please input Discount Reason"),
    //         });
    //
    //         if (!inputNote) {
    //             await this.popup.add(ErrorPopup, {
    //                 title: _t("Alert"),
    //                 body: _t("Reason for Discount is required!"),
    //             });
    //             return false;
    //         }
    //
    //         if (confirmed) {
    //             this.pos.selectedOrder.discount_reason = inputNote;
    //
    //             // السماح بإدخال نوع الخصم وقيمته من خلال لوحة الأرقام
    //             const {confirmed, payload: discountValue} = await this.popup.add(NumberPopup, {
    //                 title: _t("Discount Value"),
    //                 startingValue: this.pos.config.discount_pc,
    //                 isInputSelected: true,
    //             });
    //
    //             if (confirmed) {
    //                 const discountType = await this.popup.add(NumberPopup, {
    //                     title: _t("Is this a percentage (enter 1) or fixed amount (enter any number)?"),
    //                     startingValue: 1,
    //                     isInputSelected: true,
    //                 });
    //
    //                 if (discountType.confirmed) {
    //                     const isPercentage = parseFloat(discountType.payload) === 1;
    //                     await self.apply_discount(parseFloat(discountValue), isPercentage);
    //                 }
    //             }
    //         }
    //     } else {
    //
    //         // إذا كان الخصم غير ممكّن، يطلب كلمة مرور من المستخدم
    //         const {confirmed, payload: inputPin} = await this.popup.add(NumberPopup, {
    //             isPassword: true,
    //             title: _t("Password?"),
    //         });
    //
    //         if (confirmed) {
    //             const pinHash = Sha1.hash(inputPin);
    //             const employee = this.pos.employees.find(emp => pinHash === "" + emp.pin);
    //
    //             if (employee) {
    //                 // التحقق من صلاحيات الموظف المدخل
    //                 if (employee.enable_emp_global_discount) {
    //                     const {confirmed, payload: inputNote} = await this.popup.add(TextAreaPopup, {
    //                         title: _t("Please input Discount Reason"),
    //                     });
    //
    //                     if (!inputNote) {
    //                         await this.popup.add(ErrorPopup, {
    //                             title: _t("Alert"),
    //                             body: _t("Reason for Discount is required!"),
    //                         });
    //                         return false;
    //                     }
    //
    //                     if (confirmed) {
    //                         this.pos.selectedOrder.discount_reason = inputNote;
    //
    //                         const {confirmed, payload: discountValue} = await this.popup.add(NumberPopup, {
    //                             title: _t("Discount Value"),
    //                             startingValue: this.pos.config.discount_pc,
    //                             isInputSelected: true,
    //                         });
    //
    //                         if (confirmed) {
    //                             const discountType = await this.popup.add(NumberPopup, {
    //                                 title: _t("Is this a percentage (enter 1) or fixed amount (enter 0)?"),
    //                                 startingValue: 1,
    //                                 isInputSelected: true,
    //                             });
    //
    //                             if (discountType.confirmed) {
    //                                 const isPercentage = parseFloat(discountType.payload) === 1;
    //                                 await self.apply_discount(parseFloat(discountValue), isPercentage);
    //                             }
    //                         }
    //                     }
    //                 } else {
    //                     await this.popup.add(ErrorPopup, {
    //                         title: _t("Discount Not Allowed"),
    //                         body: _t("You are not authorized to apply global discounts."),
    //                     });
    //                     return false;
    //                 }
    //             } else {
    //                 await this.popup.add(ErrorPopup, {
    //                     title: _t("Incorrect Password"),
    //                     body: _t("Please try again."),
    //                 });
    //                 return false;
    //             }
    //         } else {
    //             return false;
    //         }
    //     }
    // }
async click() {
    var self = this;

    // التحقق من تمكين الخصم العالمي للموظف الحالي
    if (this.pos.cashier.enable_emp_global_discount) {
        // إذا كان الخصم العالمي ممكناً، يطلب إدخال سبب الخصم
        const {confirmed: reasonConfirmed, payload: inputNote} = await this.popup.add(TextAreaPopup, {
            title: _t("Please input Discount Reason"),
        });

        if (!reasonConfirmed || !inputNote) {
            await this.popup.add(ErrorPopup, {
                title: _t("Alert"),
                body: _t("Reason for Discount is required!"),
            });
            return false;
        }

        this.pos.selectedOrder.discount_reason = inputNote;

        // عرض نافذة اختيار نوع الخصم قبل إدخال القيمة
        const {confirmed: typeConfirmed, payload: discountType} = await this.popup.add(SelectionPopup, {
            title: _t("Select Discount Type"),
            list: [
                {id: "0", label: _t("Percentage"), item: "percentage"},
                {id: "1", label: _t("Fixed Amount"), item: "fixed"},
            ]
        });

        if (typeConfirmed) {
            console.log('Discount Type Selected:', discountType);

            // السماح بإدخال قيمة الخصم بناءً على نوع الخصم المختار
            const {confirmed: valueConfirmed, payload: discountValue} = await this.popup.add(NumberPopup, {
                title: discountType === 'percentage' ? _t("Enter Discount Percentage") : _t("Enter Fixed Discount Amount"),
                startingValue: discountType === 'percentage' ? this.pos.config.discount_pc : 0,
                isInputSelected: true,
            });

            if (valueConfirmed) {
                if (discountType == 'percentage') {
                    console.log('Applying percentage discount');
                    const discount = Math.max(0, Math.min(100, parseFloat(discountValue))); // للتأكد أن النسبة بين 0 و 100
                    await self.apply_discount(discount, true); // true تعني أنه خصم نسبة مئوية
                } else if (discountType == 'fixed') {
                    console.log('Applying fixed amount discount');
                    const discount = parseFloat(discountValue); // تأكد من أن القيمة رقمية
                    await self.apply_discount(discount, false); // false تعني أنه خصم بمبلغ ثابت
                } else {
                    console.error('Unknown discount type:', discountType);
                }
            }
        }
    } else {
        await this.popup.add(ErrorPopup, {
            title: _t("Discount Not Allowed"),
            body: _t("You are not authorized to apply global discounts."),
        });
        return false;
    }
}

    async apply_discount(value, isPercentage) {
        const order = this.pos.get_order();
        const lines = order.get_orderlines();
        const product = this.pos.db.get_product_by_id(this.pos.config.discount_product_id[0]);

        if (product === undefined) {
            await this.popup.add(ErrorPopup, {
                title: _t("No discount product found"),
                body: _t(
                    "The discount product seems misconfigured. Make sure it is flagged as 'Can be Sold' and 'Available in Point of Sale'."
                ),
            });
            return;
        }

        // إزالة الخصومات الحالية
        lines
            .filter((line) => line.get_product() === product)
            .forEach((line) => order._unlinkOrderline(line));

        // إضافة الخصم كمنتج
        const linesByTax = order.get_orderlines_grouped_by_tax_ids();
        for (const [tax_ids, lines] of Object.entries(linesByTax)) {
            const tax_ids_array = tax_ids
                .split(",")
                .filter((id) => id !== "")
                .map((id) => Number(id));

            let discount = 0;
            if (isPercentage) {
                const baseToDiscount = order.calculate_base_amount(
                    tax_ids_array,
                    lines.filter((ll) => ll.isGlobalDiscountApplicable())
                );
                discount = (-value / 100.0) * baseToDiscount;
            } else {
                discount = -value;
            }

            if (discount < 0) {
                order.add_product(product, {
                    price: discount,
                    lst_price: discount,
                    tax_ids: tax_ids_array,
                    merge: false,
                    description:
                        `${isPercentage ? value + "%" : _t("Fixed amount")}, ` +
                        (tax_ids_array.length
                            ? _t(
                                "Tax: %s",
                                tax_ids_array
                                    .map((taxId) => this.pos.taxes_by_id[taxId].amount + "%")
                                    .join(", ")
                            )
                            : _t("No tax")),
                    extras: {
                        price_type: "automatic",
                    },
                });
            }
        }
    }
}

ProductScreen.addControlButton({
    component: DiscountButton,
    condition: function () {
        const {module_pos_discount, discount_product_id} = this.pos.config;
        const cashier = this.pos.user.disable_global_discount;
        return module_pos_discount && discount_product_id && !cashier;
    },
    position: ["replace", "DiscountButton"],
});
