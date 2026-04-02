odoo.define('sahara_planet.AddTaxFree', function (require) {
    "use strict";

    var models = require("point_of_sale.models");
    var _super_order = models.Order.prototype;
    const PaymentScreen = require('point_of_sale.PaymentScreen');


    models.Order = models.Order.extend({

        initialize: function (attr, options) {

            this.tax_free_pos = 'No Tax free';


            _super_order.initialize.apply(this, arguments);

        },
        set_tax_note: function (tax_free_pos) {
            this.tax_free_pos = tax_free_pos;
            this.trigger('change', this);
        },
        get_tax_note: function () {
            return this.tax_free_pos;
        },


        export_as_JSON: function () {
            var json = _super_order.export_as_JSON.apply(this, arguments);


            json.tax_free_pos = this.tax_free_pos;


            return json
        },

        export_for_printing: function () {


            var orders = _super_order.export_for_printing.apply(this, arguments);


            let selectedOrder = this.pos.get_order();
            selectedOrder.tax_free_pos = this.tax_free_pos

            return orders;
        },


    });
});