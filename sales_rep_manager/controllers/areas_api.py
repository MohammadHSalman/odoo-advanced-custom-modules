# -*- coding: utf-8 -*-
# Done+++++++++++++++++++++++++++++++

import logging
from odoo import http
from odoo.http import request
from .api_utils import json_response, jwt_required, format_response, noneify  # ⟵ أضف noneify

_logger = logging.getLogger(__name__)


class AreasAPI(http.Controller):

    # --- Serializer ---
    def _serialize_state(self, st, selected=False):
        return {
            "id": st.id,
            "name": noneify(st.name),                    # ⟵ null بدل false
            "code": noneify(st.code),                    # ⟵ null بدل false
            "country": {
                "id": st.country_id.id if st.country_id else None,
                "name": noneify(st.country_id.name if st.country_id else None),
                "code": noneify(st.country_id.code if st.country_id else None),
            },
            "selected": bool(selected),
        }

    @http.route(
        ['/sales_rep_manager/<string:api_version>/areas'],
        type='http', auth='none', methods=['GET', 'OPTIONS'], csrf=False, cors='*'
    )
    @jwt_required()
    def get_areas(self, **kwargs):
        # CORS preflight
        if request.httprequest.method == 'OPTIONS':
            return json_response({"ok": True}, status=200)

        try:
            env = kwargs["_jwt_env"]

            Country = env['res.country'].sudo()
            State = env['res.country.state'].sudo()

            # 1) تحديد الدولة (Governorate) بأولوية
            country = None

            governorate_id = request.params.get('governorate_id')
            if governorate_id:
                try:
                    g_id = int(governorate_id)
                    c_try = Country.browse(g_id)
                    if c_try.exists():
                        country = c_try
                except Exception:
                    pass

            if not country:
                governorate_code = request.params.get('governorate_code')
                if governorate_code:
                    code = str(governorate_code).upper()
                    c_try = Country.search([('code', '=', code)], limit=1)
                    if c_try:
                        country = c_try

            if not country:
                model_name = request.params.get('model')
                res_id = request.params.get('res_id')
                if model_name and res_id:
                    try:
                        rec_env = env[model_name].sudo()
                        record = rec_env.browse(int(res_id))
                        if record.exists() and hasattr(record, 'governorate_id') and record.governorate_id:
                            country = record.governorate_id
                    except Exception:
                        pass

            if not country:
                try:
                    country = env.ref('base.sy', raise_if_not_found=False)
                except Exception:
                    country = None

            if not country:
                return format_response(
                    False,
                    "Governorate (Country) not found or not configured (base.sy)",
                    error_code=-404,
                    http_status=404
                )

            # 2) الدومين
            domain = [('country_id', '=', country.id)]
            q = request.params.get('q')
            if q:
                domain += ['|', ('name', 'ilike', q), ('code', 'ilike', q)]

            try:
                limit = int(request.params.get('limit', 80))
            except Exception:
                limit = 80
            try:
                offset = int(request.params.get('offset', 0))
            except Exception:
                offset = 0
            order = request.params.get('order', 'name asc')

            states = State.search(domain, limit=limit, offset=offset, order=order)
            total = State.search_count(domain)

            # 3) selected
            selected_ids = set()
            selected_only = str(request.params.get('selected_only', '0')).lower() in ('1', 'true', 't', 'yes', 'y')

            model_name = request.params.get('model')
            res_id = request.params.get('res_id')
            if model_name and res_id:
                try:
                    rec_env = env[model_name].sudo()
                    record = rec_env.browse(int(res_id))
                    if record.exists() and hasattr(record, 'area_ids'):
                        selected_ids = set(record.area_ids.ids)
                except Exception:
                    pass

            if selected_only and selected_ids:
                states = states.filtered(lambda s: s.id in selected_ids)

            results = [self._serialize_state(s, selected=(s.id in selected_ids)) for s in states]

            return format_response(
                True, "Areas fetched successfully",
                {
                    "governorate": {
                        "id": country.id,
                        "name": noneify(country.name),   # ⟵ null عند الفراغ
                        "code": noneify(country.code),   # ⟵ null عند الفراغ
                    },
                    "total": total,
                    "count": len(states),
                    "limit": limit,
                    "offset": offset,
                    "results": results
                },
                http_status=200
            )

        except Exception as e:
            _logger.exception("Error fetching areas")
            return format_response(False, f"Internal error: {str(e)}", error_code=-500, http_status=500)
