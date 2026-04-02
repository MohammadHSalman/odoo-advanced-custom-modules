/** @odoo-module */

import {patch} from "@web/core/utils/patch";
import { FloorScreen } from "@pos_restaurant/app/floor_screen/floor_screen";


patch(FloorScreen.prototype, {
    async onSelectTable(table, ev) {
        const currentDateTime = new Date();  // الحصول على الوقت والتاريخ الحاليين
          // طباعة الوقت والتاريخ بالتنسيق المحلي

        if (this.pos.isEditMode) {
            if (ev.ctrlKey || ev.metaKey) {
                this.state.selectedTableIds.push(table.id);
            } else {
                this.state.selectedTableIds = [];
                this.state.selectedTableIds.push(table.id);
            }
        } else {
            if (this.pos.orderToTransfer) {
                await this.pos.transferTable(table);
            } else {
                try {
                    await this.pos.setTable(table);
                } catch (e) {
                    if (!(e instanceof ConnectionLostError)) {
                        throw e;
                    }
                    // Reject error in a separate stack to display the offline popup, but continue the flow
                    Promise.reject(e);
                }
            }
            const order = this.pos.get_order();
            order.create_time =  currentDateTime.toLocaleString()
            this.pos.showScreen(order.get_screen_data().name);
        }
    }

});




