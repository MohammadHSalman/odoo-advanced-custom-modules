# -*- coding: utf-8 -*-
# Done+++++++++++++++++++++++++++++++
import logging
from odoo import http
from odoo.http import request
from .api_utils import json_response, jwt_required, format_response, noneify

_logger = logging.getLogger(__name__)


class PartnerIndustriesAPI(http.Controller):

    # ---- Serializer ----
    def _serialize_industry(self, ind):
        return {
            "id": ind.id,
            "name": noneify(ind.name),
            "full_name": noneify(getattr(ind, "full_name", None)),
            "active": ind.active,
        }

    @http.route([
        '/sales_rep_manager/<string:api_version>/industries',
        '/sales_rep_manager/<string:api_version>/industries/<int:industry_id>',
    ], type='http', auth='none', methods=['GET', 'OPTIONS'], csrf=False, cors='*')
    @jwt_required()  # يتطلب Bearer Access Token
    def industries(self, industry_id=None, **kwargs):  # ⟵ حذفنا api_version من التوقيع
        # CORS preflight
        if request.httprequest.method == 'OPTIONS':
            return json_response({"ok": True}, status=200)

        try:
            # خذ env من الديكوريتور (بدون session_id)
            env = kwargs["_jwt_env"]

            # ضبط السياق (لغة + active_test)
            active_test = str(request.params.get('active_test', '1')).lower() not in ('0', 'false', 'no')
            env_ctx = dict(env.context, active_test=active_test)

            lang = request.params.get('lang')
            if lang:
                env_ctx['lang'] = lang

            Industry = env['res.partner.industry'].with_context(env_ctx).sudo()

            # ---- صناعة واحدة ----
            if industry_id:
                ind = Industry.browse(int(industry_id))
                if not ind.exists():
                    return format_response(False, "Industry not found", error_code=-404, http_status=404)
                return format_response(True, "Industry fetched successfully", self._serialize_industry(ind),
                                       http_status=200)

            # ---- قائمة الصناعات ----
            domain = []

            # ids (اختياري) كقائمة مفصولة بفواصل
            ids_param = request.params.get('ids')
            if ids_param:
                try:
                    ids_list = [int(x) for x in str(ids_param).split(',') if x.strip().isdigit()]
                    if ids_list:
                        domain.append(('id', 'in', ids_list))
                except Exception:
                    pass

            # active (اختياري)
            if 'active' in request.params:
                is_active = str(request.params.get('active')).lower() in ('1', 'true', 't', 'yes', 'y')
                domain.append(('active', '=', is_active))

            # q search
            q = request.params.get('q')
            if q:
                domain += ['|', ('name', 'ilike', q), ('full_name', 'ilike', q)]

            # ترقيم وترتيب
            try:
                limit = int(request.params.get('limit', 80))
            except Exception:
                limit = 80
            try:
                offset = int(request.params.get('offset', 0))
            except Exception:
                offset = 0
            order = request.params.get('order', 'name asc')

            total = Industry.search_count(domain)
            records = Industry.search(domain, limit=limit, offset=offset, order=order)

            results = [self._serialize_industry(ind) for ind in records]

            return format_response(True, "Industries fetched successfully", {
                "total": total,
                "count": len(records),
                "limit": limit,
                "offset": offset,
                "results": results
            }, http_status=200)

        except Exception as e:
            _logger.exception("Error fetching industries")
            return format_response(False, f"Internal error: {str(e)}", error_code=-500, http_status=500)
