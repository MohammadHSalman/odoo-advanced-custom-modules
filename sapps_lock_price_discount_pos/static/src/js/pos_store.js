/** @odoo-module */

import {PosStore} from "@point_of_sale/app/store/pos_store";
import {patch} from "@web/core/utils/patch";

patch(PosStore.prototype, {
    // Add a new property to store the current table name
    currentTableName: '',

    setCurrentOrderToTransfer() {
        this.orderToTransfer = this.selectedOrder;
        const currentTableId = this.orderToTransfer.tableId; // Get current table ID

        // Get the current table object from tables_by_id
        const currentTable = this.tables_by_id[currentTableId];
        this.selectedOrder.source_table = currentTable ? currentTable.name : '';

        // Store the name of the current table
        if (currentTable) {
            this.currentTableName = currentTable.name;
            console.log(`Current table name: ${currentTable.name}`);
        } else {
            this.currentTableName = '';
            console.log("Table not found");
        }
    },

    async transferTable(table) {
        const sourceTable = table;

        this.table = table;
        try {
            this.loadingOrderState = true;
            await this._syncTableOrdersFromServer(table.id);
        } finally {
            this.loadingOrderState = false;
            this.orderToTransfer.tableId = table.id;
            this.set_order(this.orderToTransfer);
            this.transferredOrdersSet.add(this.orderToTransfer);
            this.orderToTransfer = null;
            this.selectedOrder.is_transfer = true;

            // Check if current table name and new table name are the same
            if (this.currentTableName !== table.name) {
                this.selectedOrder.source_table = this.currentTableName;
            } else {
                this.selectedOrder.source_table = '';
            }

            // Use the stored current table name
            console.log(`Transferring order from table: ${this.currentTableName} to table: ${table.name}`);
        }
    },
});
