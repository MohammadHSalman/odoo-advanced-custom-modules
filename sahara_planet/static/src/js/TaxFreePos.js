odoo.define('sahara_planet.TaxFreePos', function (require) {
    'use strict';
    const {Gui} = require('point_of_sale.Gui');
    const PosComponent = require('point_of_sale.PosComponent');
    const {posbus} = require('point_of_sale.utils');
    const ProductScreen = require('point_of_sale.ProductScreen');
    const {useListener} = require('web.custom_hooks');
    const Registries = require('point_of_sale.Registries');
    const PaymentScreen = require('point_of_sale.PaymentScreen');

    const CustomButtonPaymentScreen = (PaymentScreen) =>

        class extends PaymentScreen {


            constructor() {

                super(...arguments);
                useListener('Is-Tax-Free', this.IsTaxFree)


            }

            IsTaxFree() {

                var checkbox_status = document.getElementById("checkbox_cgv").checked;
                if (checkbox_status == true) {
                    return this.currentOrder.set_tax_note('Tax free')
                } else {
                    return this.currentOrder.set_tax_note('No Tax free')
                }



            }


        };
    Registries.Component.extend(PaymentScreen, CustomButtonPaymentScreen);
    return CustomButtonPaymentScreen;
});
