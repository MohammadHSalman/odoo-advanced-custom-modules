/** @odoo-module */

import {Order, Orderline} from "@point_of_sale/app/store/models";
import {patch} from "@web/core/utils/patch";

patch(Order.prototype, {
    setup(_defaultObj, options) {
        super.setup(...arguments);
        this.code_uuid_v4 = ([1e7] + -1e3 + -4e3 + -8e3 + -1e11).replace(/[018]/g, (c) => (c ^ (crypto.getRandomValues(new Uint8Array(1))[0] & (15 >> (c / 4)))).toString(16));
        this.reprint_count = this.reprint_count || 0;

        this.create_time = this.create_time || '';
    },

    export_as_JSON() {
        const json = super.export_as_JSON(...arguments);
        json.code_uuid_v4 = this.code_uuid_v4;
        json.reprint_count = this.reprint_count;

        json.create_time = this.create_time;
        return json;
    },

    init_from_JSON(json) {
        super.init_from_JSON(...arguments);
        this.reprint_count = json.reprint_count || 0; // تعيين القيمة الافتراضية إذا لم تكن موجودة
        this.create_time = json.create_time || ''; // تعيين القيمة الافتراضية إذا لم تكن موجودة
    },

    export_for_printing() {
        const result = super.export_for_printing(...arguments);

        // إضافة reprint_count
        result.reprint_count = this.reprint_count;

        let selectedOrder = this.pos.get_order();
        selectedOrder.code_uuid_v4 = this.code_uuid_v4;
        let total_amount = 0;

        // حساب المجموع الإجمالي
        this.orderlines.forEach(line => {
            const line_total = line.get_quantity() * line.get_unit_price();
            total_amount += line_total;
        });

        // إزالة الفراغات وإشارة '-' من result.name
        let sanitized_name = this.uid.replace(/[\s-]/g, '');
        result.server_id = this.server_id;
        // إعداد بيانات QR
        var qrData = "#";
        qrData += result.headerData.company.vat;  // VAT
        qrData += "_";  // Separator
        qrData += result.headerData.company.name;  // Facility Name
        qrData += "_";  // Separator
        qrData += this.pos.config.pos_num;  // POS Number
        qrData += "#";  // Separator
        qrData += this.server_id;  // Sanitized POS Reference
        qrData += "_";  // Separator
        const orderDate = result.date;  // Date
        qrData += orderDate;  // Date
        qrData += "_";  // Separator
        qrData += total_amount;  // Total Amount
        qrData += "_";  // Separator
        qrData += result.headerData.company.currency_id[1];  // Currency
        qrData += "_";  // Separator
        qrData += "SAPPS Odoo";  // Additional Info
        qrData += "#";  // Separator
        qrData += this.code_uuid_v4;  // UUID
        qrData += "#";
        // توليد QR code
        const codeWriter = new window.ZXing.BrowserQRCodeSvgWriter();
        let qr_code_svg = new XMLSerializer().serializeToString(codeWriter.write(qrData, 150, 150));
        result.qrcode_img = "data:image/svg+xml;base64," + window.btoa(qr_code_svg);
        result.create_time = this.create_time;

        return result;
    }
    ,

});
patch(Orderline.prototype, {
    get_all_prices(qty = this.get_quantity()) {
        // السعر الأساسي للمنتج (قبل الخصم)
        var price_unit_before_discount = this.get_unit_price();

        // الخصم الحالي
        var discount = this.get_discount();

        // السعر بعد تطبيق الخصم
        var price_unit_after_discount = price_unit_before_discount * (1.0 - discount / 100.0);
        var discount_value = price_unit_before_discount * (discount / 100.0);
        console.log('قيمة الخصم: ', discount_value);

        // المجموع الإجمالي للضرائب
        var taxtotal = 0;

        // جلب المنتج والضرائب المرتبطة به
        var product = this.get_product();
        var taxes_ids = this.tax_ids || product.taxes_id;

        // تصفية الضرائب والتحقق من وجودها
        taxes_ids = taxes_ids.filter((t) => t in this.pos.taxes_by_id);
        var taxdetail = {};

        // الحصول على الضرائب المناسبة
        var product_taxes = this.pos.get_taxes_after_fp(taxes_ids, this.order.fiscal_position);

        // التحقق إذا كان المنتج هو خصم، تجاهل الضرائب فقط
        var is_discount = product.display_name === 'Discount'; // أو أي تعريف آخر للخصم
        if (is_discount) {
            console.log('تم تجاهل الضرائب للخصم');
            product_taxes = []; // تجاهل جميع الضرائب للخصم
        }

        // حساب الضرائب بناءً على السعر الأساسي (قبل الخصم)
        var all_taxes_before_discount = this.compute_all(
            product_taxes,
            price_unit_before_discount, // السعر الأساسي
            qty,
            this.pos.currency.rounding
        );

        // حساب الضرائب بناءً على السعر بعد الخصم
        var all_taxes_after_discount = this.compute_all(
            product_taxes,
            price_unit_after_discount, // السعر بعد الخصم
            qty,
            this.pos.currency.rounding
        );

        // تقريب الضرائب وإضافتها للتفاصيل
         all_taxes_before_discount.taxes.forEach(function (tax) {
            // تقريب الضريبة لأقرب 100 (اختياري بناءً على المتطلبات)
            var roundedTaxAmount = Math.ceil(tax.amount / 100) * 100;
            taxtotal += roundedTaxAmount;
            taxdetail[tax.id] = {
                amount: roundedTaxAmount,
                base: tax.base,
            };
        });

        console.log('تفاصيل الضرائب:', taxdetail);

        // إرجاع القيم النهائية
        return {
            priceWithTax: all_taxes_after_discount.total_excluded + taxtotal, // السعر مع الضريبة بعد الخصم
            priceWithoutTax: all_taxes_after_discount.total_excluded, // السعر بدون الضريبة بعد الخصم
            priceWithTaxBeforeDiscount: all_taxes_before_discount.total_included, // السعر مع الضريبة قبل الخصم
            priceWithoutTaxBeforeDiscount: all_taxes_before_discount.total_excluded, // السعر بدون الضريبة قبل الخصم
            tax: taxtotal, // مجموع الضرائب
            taxDetails: taxdetail, // تفاصيل الضرائب
        };
    },
});
    // get_all_prices(qty = this.get_quantity()) {
    //     // السعر الأساسي للمنتج (قبل الخصم)
    //     var price_unit_before_discount = this.get_unit_price();
    //
    //     // الخصم الحالي
    //     var discount = this.get_discount();
    //
    //     // السعر بعد تطبيق الخصم
    //     var price_unit_after_discount = price_unit_before_discount * (1.0 - discount / 100.0);
    //     var discount_value = price_unit_before_discount * (discount / 100.0);
    //     console.log('قيمة الخصم: ', discount_value);
    //     // المجموع الإجمالي للضرائب
    //     var taxtotal = 0;
    //
    //     // جلب المنتج والضرائب المرتبطة به
    //     var product = this.get_product();
    //     console.log(product, '*+*+*')
    //     var taxes_ids = this.tax_ids || product.taxes_id;
    //     console.log(taxes_ids, '*+*1*')
    //     console.log(product.taxes_id, '*+21*')
    //
    //     // تصفية الضرائب والتحقق من وجودها
    //     taxes_ids = taxes_ids.filter((t) => t in this.pos.taxes_by_id);
    //     var taxdetail = {};
    //
    //     // الحصول على الضرائب المناسبة
    //     var product_taxes = this.pos.get_taxes_after_fp(taxes_ids, this.order.fiscal_position);
    //
    //     // حساب الضرائب بناءً على السعر الأساسي (قبل الخصم)
    //     var all_taxes_before_discount = this.compute_all(
    //         product_taxes,
    //         price_unit_before_discount, // السعر الأساسي
    //         qty,
    //         this.pos.currency.rounding
    //     );
    //
    //     // حساب الضرائب بناءً على السعر بعد الخصم
    //     var all_taxes_after_discount = this.compute_all(
    //         product_taxes,
    //         price_unit_after_discount, // السعر بعد الخصم
    //         qty,
    //         this.pos.currency.rounding
    //     );
    //
    //     // تقريب الضرائب وإضافتها للتفاصيل
    //     all_taxes_before_discount.taxes.forEach(function (tax) {
    //         // تقريب الضريبة لأقرب 100 (اختياري بناءً على المتطلبات)
    //         var roundedTaxAmount = Math.ceil(tax.amount / 100) * 100;
    //         taxtotal += roundedTaxAmount;
    //         taxdetail[tax.id] = {
    //             amount: roundedTaxAmount,
    //             base: tax.base,
    //         };
    //     });
    //     console.log('تفاصيل الضرائب:', taxdetail);
    //     return {
    //         priceWithTax: all_taxes_after_discount.total_excluded + taxtotal, // السعر مع الضريبة بعد الخصم
    //         priceWithoutTax: all_taxes_after_discount.total_excluded, // السعر بدون الضريبة بعد الخصم
    //         priceWithTaxBeforeDiscount: all_taxes_before_discount.total_included, // السعر مع الضريبة قبل الخصم
    //         priceWithoutTaxBeforeDiscount: all_taxes_before_discount.total_excluded, // السعر بدون الضريبة قبل الخصم
    //         tax: taxtotal, // مجموع الضرائب
    //         taxDetails: taxdetail, // تفاصيل الضرائب
    //     };
    // }
