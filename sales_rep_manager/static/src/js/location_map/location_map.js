/** @odoo-module **/

import {Component, onMounted, onWillUnmount, useRef, useState} from "@odoo/owl";
import {useService} from "@web/core/utils/hooks";
import {registry} from "@web/core/registry";

export class LocationMap extends Component {
    static template = "sales_rep_manager.LocationMap";

    setup() {
        this.orm = useService("orm");
        this.notification = useService("notification");
        this.companyService = useService("company");
        this.mapRef = useRef("map");

        this.state = useState({
            reps: [],
            searchQuery: "",
            repId: null,
            isDropdownOpen: false,
            dateFrom: this.today(),
            dateTo: this.today(),
            loading: false,
            pointCount: 0,
        });

        this._map = null;
        this._markers = [];

        onMounted(async () => {
            await this.loadLeaflet();
            this.initMap();
            await this.loadReps();
            window.addEventListener('click', this.onWindowClick.bind(this));
        });

        onWillUnmount(() => {
            if (this._map) this._map.remove();
            window.removeEventListener('click', this.onWindowClick.bind(this));
        });
    }

    async loadReps() {
        try {
            const activeCompanyIds = this.companyService.activeCompanyIds;

            this.state.reps = await this.orm.searchRead(
                "sales.rep.profile",
                [["company_id", "in", activeCompanyIds]],
                ["id", "name"],
                {order: "name asc"}
            );
        } catch (err) {
            console.error("Failed to fetch representatives:", err);
        }
    }

    get filteredReps() {
        if (!this.state.searchQuery) return this.state.reps;
        const query = this.state.searchQuery.toLowerCase();
        return this.state.reps.filter(r => r.name.toLowerCase().includes(query));
    }

    selectRep(rep) {
        this.state.repId = rep.id;
        this.state.searchQuery = rep.name;
        this.state.isDropdownOpen = false;
    }

    clearSearch() {
        this.state.searchQuery = "";
        this.state.repId = null;
        this.state.isDropdownOpen = false;
        this.clearMap();
    }

    onInputChange(ev) {
        this.state.searchQuery = ev.target.value;
        this.state.repId = null;
        this.state.isDropdownOpen = true;
    }

    onWindowClick(ev) {
        if (!ev.target.closest('.custom-search-box')) {
            this.state.isDropdownOpen = false;
        }
    }

    async draw() {
        if (!this.state.repId) {
            this.notification.add("Please select a representative first", {type: "warning"});
            return;
        }
        this.state.loading = true;
        this.clearMap();
        try {
            const domain = [
                ["sales_rep_id", "=", this.state.repId],
                ["location_time", ">=", this.state.dateFrom + " 00:00:00"],
                ["location_time", "<=", this.state.dateTo + " 23:59:59"]
            ];
            const records = await this.orm.searchRead(
                "sales.rep.location",
                domain,
                ["latitude", "longitude", "location_time"],
                {order: "location_time asc"}
            );

            if (!records.length) {
                this.notification.add("No records found", {type: "info"});
                return;
            }

            this.state.pointCount = records.length;
            const bounds = [];
            records.forEach(r => {
                const marker = window.L.marker([r.latitude, r.longitude]).addTo(this._map)
                    .bindPopup(`<b>Time:</b> ${r.location_time}`);
                this._markers.push(marker);
                bounds.push([r.latitude, r.longitude]);
            });
            this._map.fitBounds(bounds, {padding: [50, 50]});
        } catch (err) {
            this.notification.add(err.message, {type: "danger"});
        } finally {
            this.state.loading = false;
        }
    }

    async loadLeaflet() {
        if (window.L) return;
        const css = document.createElement("link");
        css.rel = "stylesheet";
        css.href = "https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/leaflet.min.css";
        document.head.appendChild(css);

        await new Promise(ok => {
            const js = document.createElement("script");
            js.src = "https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/leaflet.min.js";
            js.onload = ok;
            document.head.appendChild(js);
        });
    }

    initMap() {
        if (!this.mapRef.el) return;
        this._map = window.L.map(this.mapRef.el).setView([33.51, 36.27], 12);
        window.L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png").addTo(this._map);
    }

    clearMap() {
        this._markers.forEach(m => m.remove());
        this._markers = [];
        this.state.pointCount = 0;
    }

    today() {
        return new Date().toISOString().split("T")[0];
    }

    onDateFromChange(ev) {
        this.state.dateFrom = ev.target.value;
    }

    onDateToChange(ev) {
        this.state.dateTo = ev.target.value;
    }
}

registry.category("actions").add("sales_rep_location_map", LocationMap);