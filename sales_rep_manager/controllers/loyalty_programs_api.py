# -*- coding: utf-8 -*-
import logging
from datetime import datetime
from odoo.tools.safe_eval import safe_eval

from odoo import http
from odoo.http import request
from .api_utils import json_response, jwt_required, format_response, noneify

_logger = logging.getLogger(__name__)


class LoyaltyProgramsAPI(http.Controller):

    # ----------------------------
    # Preflight
    # ----------------------------
    def _preflight(self):
        if request.httprequest.method == 'OPTIONS':
            return json_response({"ok": True}, status=200)
        return None

    # ----------------------------
    # Serializers (Helpers)
    # ----------------------------
    def _ref(self, rec):
        if not rec:
            return None
        name = noneify(getattr(rec, "display_name", None) or getattr(rec, "name", None))
        return {"id": rec.id, "name": name}

    def _refs(self, recs):
        return [self._ref(r) for r in recs] if recs else []

    def _serialize_product(self, p):
        if not p:
            return None
        return {
            "id": p.id,
            "name": noneify(p.name),
            "default_code": noneify(getattr(p, "default_code", None)),
            "uom": self._ref(getattr(p, "uom_id", None)),
        }

    # ----------------------------
    # Domain helpers
    # ----------------------------
    def _extract_categories_from_domain(self, env, domain_str):
        if not domain_str or domain_str == '[]':
            return []
        category_ids = set()
        try:
            domain = safe_eval(domain_str)
            for cond in domain:
                if isinstance(cond, (list, tuple)) and len(cond) == 3:
                    field, operator, value = cond
                    if field == 'categ_id':
                        if isinstance(value, int):
                            category_ids.add(value)
                        elif isinstance(value, list):
                            category_ids.update(value)
        except Exception:
            pass

        if category_ids:
            return env['product.category'].sudo().browse(list(category_ids))
        return []

    # ----------------------------
    # Rule serializer
    # ----------------------------
    def _serialize_rule(self, env, r):
        products = getattr(r, "product_ids", [])
        categ_rec = getattr(r, "product_category_id", None)
        categ_list = [categ_rec] if categ_rec else []

        if not categ_list and getattr(r, "product_domain", False):
            extracted = self._extract_categories_from_domain(env, r.product_domain)
            if extracted:
                categ_list = extracted

        category_products = []
        for categ in categ_list:
            category_products += env['product.product'].sudo().search([
                ('categ_id', 'child_of', categ.id)
            ])

        all_products = list(set(products) | set(category_products))

        if products and not categ_list:
            applies_on_text = "هذا العرض مطبق على منتجات محددة"
        elif categ_list and not products:
            applies_on_text = "هذا العرض مطبق على تصنيف محدد"
        elif products and categ_list:
            applies_on_text = "هذا العرض مطبق على منتجات وتصنيف معًا"
        else:
            applies_on_text = "لا يوجد تطبيق محدد للمنتجات أو التصنيف"

        return {
            "id": r.id,
            "minimum_qty": getattr(r, "minimum_qty", 0),
            "minimum_amount": getattr(r, "minimum_amount", 0.0),
            "reward_point_mode": noneify(getattr(r, "reward_point_mode", None)),
            "product_ids": [self._serialize_product(p) for p in all_products],
            "categ_ids": self._refs(categ_list),
            "tag_id": self._ref(getattr(r, "product_tag_id", None)),
            "product_domain": noneify(getattr(r, "product_domain", None)),
            "applies_on_text": applies_on_text,
        }

    # ----------------------------
    # Reward serializer
    # ----------------------------
    def _serialize_reward(self, rw):
        reward_products = getattr(rw, "reward_product_ids", [])
        return {
            "id": rw.id,
            "reward_type": noneify(getattr(rw, "reward_type", None)),
            "description": noneify(getattr(rw, "description", None)),
            "discount": getattr(rw, "discount", 0),
            "reward_products": [self._serialize_product(p) for p in reward_products],
            "multi_product": getattr(rw, "multi_product", False),
            "reward_product_qty": getattr(rw, "reward_product_qty", 1),
        }

    # ----------------------------
    # Program serializer
    # ----------------------------
    def _serialize_program_full(self, env, p):
        return {
            "id": p.id,
            "name": noneify(getattr(p, "name", None)),
            "program_type": noneify(getattr(p, "program_type", None)),
            "date_from": p.date_from.strftime("%Y-%m-%d") if p.date_from else None,
            "date_to": p.date_to.strftime("%Y-%m-%d") if p.date_to else None,
            "currency": self._ref(getattr(p, "currency_id", None)),
            "rules": [self._serialize_rule(env, r) for r in getattr(p, "rule_ids", [])],
            "rewards": [self._serialize_reward(rw) for rw in getattr(p, "reward_ids", [])],
            "sales_channels": [{"id": c.id, "name": c.name} for c in getattr(p, "sales_channel_ids", [])],
        }

    # ----------------------------
    # GET Loyalty Programs
    # ----------------------------
    @http.route([
        "/sales_rep_manager/<string:api_version>/loyalty/programs",
        "/sales_rep_manager/<string:api_version>/loyalty/programs/<int:program_id>",
    ], type="http", auth="none", methods=["GET", "OPTIONS"], csrf=False, cors="*")
    @jwt_required()
    def get_loyalty_programs(self, program_id=None, **kwargs):

        pre = self._preflight()
        if pre:
            return pre

        try:
            env = kwargs["_jwt_env"]

            # ----------------------------
            # Request Date Logic
            # ----------------------------
            date_str = request.params.get("date")
            if date_str:
                request_date = datetime.strptime(date_str, "%Y-%m-%d").date()
            else:
                request_date = datetime.today().date()

            # Active Test
            active_test = str(request.params.get("active_test", "1")).lower() not in ("0", "false", "no")
            Program = env["loyalty.program"].with_context(active_test=active_test).sudo()

            # ----------------------------
            # Single Program
            # ----------------------------
            if program_id:
                p = Program.browse(program_id)
                if not p.exists():
                    return format_response(False, "Loyalty Program not found", error_code=-404, http_status=404)

                return format_response(
                    True,
                    "Loyalty Program fetched successfully",
                    self._serialize_program_full(env, p),
                    http_status=200
                )

            # ----------------------------
            # Domain building
            # ----------------------------
            domain = []

            # Active filter
            if "active" in request.params:
                is_active = str(request.params.get("active")).lower() in ("1", "true", "yes")
                domain.append(("active", "=", is_active))

            # Company filter
            company_id = request.params.get("company_id")
            if company_id:
                if str(company_id).lower() == "false":
                    domain.append(("company_id", "=", False))
                else:
                    domain.append(("company_id", "in", [int(company_id), False]))

            # Program type logic
            requested_type = request.params.get("program_type")
            if requested_type:
                domain.append(("program_type", "=", requested_type))
            else:
                domain.append(('reward_ids.reward_type', '=', 'product'))

            # Name search
            q = request.params.get("q")
            if q:
                domain.append(("name", "ilike", q))

            # ----------------------------
            # DATE VALIDITY LOGIC ⭐
            # ----------------------------
            domain += [
                '|', ('date_from', '=', False), ('date_from', '<=', request_date),
                '|', ('date_to', '=', False), ('date_to', '>=', request_date),
            ]

            # Pagination
            limit = int(request.params.get("limit", 80))
            offset = int(request.params.get("offset", 0))

            total = Program.search_count(domain)
            programs = Program.search(domain, limit=limit, offset=offset, order="sequence, id")

            return format_response(True, "Loyalty Programs fetched successfully", {
                "total": total,
                "count": len(programs),
                "limit": limit,
                "offset": offset,
                "results": [self._serialize_program_full(env, p) for p in programs]
            }, http_status=200)

        except Exception as e:
            _logger.exception("Error fetching loyalty programs")
            return format_response(False, f"Internal error: {str(e)}", error_code=-500, http_status=500)
