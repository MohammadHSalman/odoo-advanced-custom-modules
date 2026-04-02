/** @odoo-module **/

import {OrderWidget} from "@point_of_sale/app/generic_components/order_widget/order_widget";
import {patch} from "@web/core/utils/patch";
import {Orderline, Order} from "@point_of_sale/app/store/models";

// Helper function to format the timestamp correctly
function formatTimestamp(date) {
    const pad = (num) => String(num).padStart(2, '0');
    return (
        date.getFullYear() +
        '-' +
        pad(date.getMonth() + 1) +
        '-' +
        pad(date.getDate()) +
        ' ' +
        pad(date.getHours()) +
        ':' +
        pad(date.getMinutes()) +
        ':' +
        pad(date.getSeconds())
    );
}

// Helper function to handle audit logging
async function auditLog(action, orderline, env) {
    // Format the timestamp correctly
    const timestamp = formatTimestamp(new Date());

    // Retrieve or set default user_id
    const user_id = orderline.order.cashier?.id; // Default user_id

    // Retrieve or set default pos_order_id
    const pos_order_id = orderline.order?.server_id || 1; // Default pos_order_id


    // Validate and prepare data
    const auditLogData = {
        action: action, // Action can be 'create', 'remove', 'update', etc.
        user_id: user_id, // Corrected to use the dynamic user_id
        pos_order_id: pos_order_id, // Corrected to use the dynamic pos_order_id
        // create_time: orderline.order.create_time, // Should be an integer
        receipt_num: orderline.order.name, // Should be an integer
        product_id: orderline.product?.id || null, // Should be an integer
        quantity: orderline.quantity || null, // Should be a number
        price_unit: orderline.price || 1, // Default value
        timestamp: timestamp, // Should be a string in the format '%Y-%m-%d %H:%M:%S'
    };


    try {
        const result = await env.services.orm.create('pos.order.audit.log', [auditLogData]);
    } catch (error) {

    }
}

// Save original methods to avoid recursion
const originalSetup = Orderline.prototype.setup;
const originalSetQuantity = Orderline.prototype.set_quantity;

// Patch the Orderline model to include auditing on key actions
patch(Orderline.prototype, {
    setup() {
        // Call the original setup method
        originalSetup.apply(this, arguments);

        // Log the creation of the order line
        auditLog('create', this, this.env);
    },

    set_quantity(quantity, keep_price) {
        let res = super.set_quantity(...arguments);
        if (quantity == 0) {
            // If quantity is 0, manually remove the orderline
            auditLog('remove', this, this.env);
            // this.order.remove_orderline(this); // Ensure the orderline is removed from the order
            // this.pos.removeOrder(this);
        } else {
            // Log the update action
            auditLog('update', this, this.env);
            originalSetQuantity.apply(this, arguments);
        }

        return res
    },

});

patch(Order.prototype, {
    removeOrderline(line) {
        auditLog('delete', line, this.env);
        var res = super.removeOrderline(line)
        return res
    }
});
