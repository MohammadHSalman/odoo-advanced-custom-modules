odoo.define('sahara_planet.SendAndRefund', function (require) {
    "use strict";
    var models = require('point_of_sale.models');
    var core = require('web.core');
    var rpc = require('web.rpc');
    var Dialog = require('web.Dialog');


    var posModelSuper = models.PosModel.prototype;
    models.PosModel = models.PosModel.extend({
        async send_invoice() {
            try {
                var result = await rpc.query({
                    model: 'pos.order',
                    method: 'send_order_pos',
                    args: [[]],
                });
                if (result.startsWith("Could not issue tax refund")) {
                    Dialog.alert(self, result, {title: 'Error', size: 'medium', dialogClass: 'custom-dialog-class'});
                } else if (result.startsWith("Tax-Free tag successfully")) {
                    Dialog.alert(self, result, {title: 'Success', size: 'medium', dialogClass: 'custom-dialog-class'});
                } else if (result.startsWith("Tag has been voided")) {
                    Dialog.alert(self, result, {title: 'Success', size: 'medium', dialogClass: 'custom-dialog-class'});
                } else if (result.startsWith("Can't void tag")) {
                    Dialog.alert(self, result, {title: 'Error', size: 'medium', dialogClass: 'custom-dialog-class'});
                } else if (result.startsWith("Transaction does not exist")) {
                    Dialog.alert(self, result, {title: 'Error', size: 'medium', dialogClass: 'custom-dialog-class'});
                } else if (result) {
                    Dialog.alert(self, result, {title: 'Success', size: 'medium', dialogClass: 'custom-dialog-class'});
                }
            } catch (e) {
                console.error(e);
            }
        }
        ,


        edit_tag_number() {
            this.rpc({
                model: 'pos.order',
                method: 'get_tag',
                args: [[]],


            });
        },

        push_and_invoice_order: function (order) {
            var self = this;
            return new Promise((resolve, reject) => {
                if (!order.get_client()) {
                    reject({code: 400, message: 'Missing Customer', data: {}});
                } else {

                    var order_id = self.db.add_order(order.export_as_JSON());


                    self.flush_mutex.exec(async () => {


                        try {

                            const server_ids = await self._flush_orders([self.db.get_order(order_id)], {
                                timeout: 30000,
                                to_invoice: true,
                            });
                            try {
                                await this.send_invoice()
                            } catch (e) {

                            }


                            if (server_ids.length) {

                                const [orderWithInvoice] = await self.rpc({
                                    method: 'read',
                                    model: 'pos.order',
                                    args: [server_ids, ['account_move']],
                                    kwargs: {load: false},
                                });

                                await self
                                    .do_action('account.account_invoices', {
                                        additional_context: {
                                            active_ids: [orderWithInvoice.account_move],
                                        },
                                    })
                                    .catch(() => {
                                        reject({code: 401, message: 'Backend Invoice', data: {order: order}});

                                    });

                            } else {
                                reject({code: 401, message: 'Backend Invoice', data: {order: order}});
                            }
                            resolve(server_ids);
                        } catch (error) {
                            reject(error);
                        }
                    });
                }
            });
        },
    });

});
