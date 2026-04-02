/** @odoo-module */

import {Order,Orderline} from "@point_of_sale/app/store/models";
import {patch} from "@web/core/utils/patch";

patch(Order.prototype, {
    setup(_defaultObj, options) {
        super.setup(...arguments);
        this.discount_reason = this.discount_reason; // تعيين القيمة الافتراضية إلى 0
        this.is_transfer = this.is_transfer; // تعيين القيمة الافتراضية إلى 0
        this.source_table = this.source_table; // تعيين القيمة الافتراضية إلى 0
    },
    //@override
    export_as_JSON() {
        const json = super.export_as_JSON(...arguments);
        json.discount_reason = this.discount_reason; // تأكد من تضمين discount_reason في JSON
        json.is_transfer = this.is_transfer; // تأكد من تضمين discount_reason في JSON
        json.source_table = this.source_table; // تأكد من تضمين discount_reason في JSON
        return json;
    },
    //@override
    init_from_JSON(json) {
        super.init_from_JSON(...arguments);
        this.discount_reason = json.discount_reason; // تعيين القيمة الافتراضية إذا لم تكن موجودة
        this.is_transfer = json.is_transfer; // تعيين القيمة الافتراضية إذا لم تكن موجودة
        this.source_table = json.source_table; // تعيين القيمة الافتراضية إذا لم تكن موجودة
    },
    export_for_printing() {
        const result = super.export_for_printing(...arguments);
        result.discount_reason = this.discount_reason;
        result.is_transfer = this.is_transfer;
        return result;
    },
});

patch(Orderline.prototype, {
    setup(_defaultObj, options) {
        super.setup(...arguments);
        this.discount_line_reason = this.discount_line_reason;
    },
    init_from_JSON(json) {
        var self = this
        super.init_from_JSON(...arguments);
        this.discount_line_reason = json.discount_line_reason;
    },
    export_as_JSON() {
        var res = super.export_as_JSON(...arguments);
        res['discount_line_reason'] = this.discount_line_reason;
        return res
    },
});