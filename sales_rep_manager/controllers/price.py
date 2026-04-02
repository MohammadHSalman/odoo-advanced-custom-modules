# -*- coding: utf-8 -*-
import logging
from datetime import datetime

from odoo import http
from odoo.http import request
from .api_utils import json_response, jwt_required, format_response, noneify

_logger = logging.getLogger(__name__)


class PricelistsReadOnlyAPI(http.Controller):

    # CORS preflight
    def _preflight(self):
        if request.httprequest.method == 'OPTIONS':
            return json_response({"ok": True}, status=200)
        return None

    # ----------------------------
    # Date validation helper (NEW)
    # ----------------------------
    def _is_item_valid_by_date(self, it, request_date):
        if it.date_start and request_date < it.date_start:
            return False
        if it.date_end and request_date > it.date_end:
            return False
        return True

    # ---- Serializers ----
    def _serialize_item_full(self, it, env=None):
        compute_price_raw = getattr(it, 'compute_price', None)
        compute_price_norm = 'percentage' if compute_price_raw == 'percent' else compute_price_raw
        is_percentage_mode = (compute_price_raw in ('percent', 'percentage'))
        percent_val = getattr(it, 'percent_price', None) if is_percentage_mode else None

        applied_items = []
        applied_type_msg = None

        if it.applied_on == '2_product_category' and it.categ_id and env:
            applied_type_msg = "Applied on Category"
            products_in_category = env['product.product'].sudo().search([
                ('categ_id', 'child_of', it.categ_id.id)
            ])
            applied_items = [
                {"id": p.id, "name": noneify(p.display_name or p.name)}
                for p in products_in_category
            ]

        elif it.product_id:
            applied_type_msg = "Applied on Product"
            applied_items = [
                {"id": it.product_id.id,
                 "name": noneify(it.product_id.display_name or it.product_id.name)}
            ]

        elif it.product_tmpl_id:
            applied_type_msg = "Applied on Product Template"
            applied_items = [
                {"id": it.product_tmpl_id.id,
                 "name": noneify(it.product_tmpl_id.display_name or it.product_tmpl_id.name)}
            ]

        return {
            "id": it.id,
            "compute_price": noneify(compute_price_norm),
            "compute_price_raw": noneify(compute_price_raw),
            "percent_price": percent_val,
            "applied_on": noneify(getattr(it, "applied_on", None)),
            "applied_type_msg": applied_type_msg,
            "min_quantity": it.min_quantity,
            "fixed_price": it.fixed_price,
            "price_discount": it.price_discount,
            "price_surcharge": it.price_surcharge,
            "price_round": it.price_round,
            "price_min_margin": it.price_min_margin,
            "price_max_margin": it.price_max_margin,
            "date_start": it.date_start and it.date_start.strftime("%Y-%m-%d") or None,
            "date_end": it.date_end and it.date_end.strftime("%Y-%m-%d") or None,
            "base": noneify(getattr(it, "base", None)),
            "applied_items": applied_items,
            "base_pricelist_id": it.base_pricelist_id and {
                "id": it.base_pricelist_id.id,
                "name": noneify(it.base_pricelist_id.display_name or it.base_pricelist_id.name),
            } or None,
            "categ_id": it.categ_id and {
                "id": it.categ_id.id,
                "name": noneify(it.categ_id.display_name or it.categ_id.name),
            } or None,
            "product_tmpl_id": it.product_tmpl_id and {
                "id": it.product_tmpl_id.id,
                "name": noneify(it.product_tmpl_id.display_name or it.product_tmpl_id.name),
            } or None,
            "product_id": it.product_id and {
                "id": it.product_id.id,
                "name": noneify(it.product_id.display_name or it.product_id.name),
                "uom_id": it.product_id.uom_id and {
                    "id": it.product_id.uom_id.id,
                    "name": noneify(it.product_id.uom_id.name),
                } or None,
            } or None,
            "company_id": it.company_id and {
                "id": it.company_id.id,
                "name": noneify(it.company_id.name),
            } or None,
            "currency_id": it.currency_id and {
                "id": it.currency_id.id,
                "name": noneify(it.currency_id.name),
            } or None,
        }

    def _serialize_pricelist_full(self, pl, env=None, request_date=None):
        return {
            "id": pl.id,
            "name": noneify(pl.name),
            "display_name": noneify(getattr(pl, "display_name", None) or pl.name),
            "active": pl.active,
            "sequence": pl.sequence,
            "currency": {
                "id": pl.currency_id.id,
                "name": noneify(pl.currency_id.name),
            },
            "company": pl.company_id and {
                "id": pl.company_id.id,
                "name": noneify(pl.company_id.name),
            } or None,
            "country_groups": [
                {"id": g.id, "name": noneify(g.name)}
                for g in pl.country_group_ids
            ],
            "items_count": len(pl.item_ids),
            "items": [
                self._serialize_item_full(it, env=env)
                for it in pl.item_ids
                if self._is_item_valid_by_date(it, request_date)
            ],
        }

    def _serialize_pricelist_brief(self, pl, with_items=False, env=None, request_date=None):
        data = {
            "id": pl.id,
            "name": noneify(pl.name),
            "display_name": noneify(getattr(pl, "display_name", None) or pl.name),
            "active": pl.active,
            "sequence": pl.sequence,
            "currency": {
                "id": pl.currency_id.id,
                "name": noneify(pl.currency_id.name),
            },
            "company": pl.company_id and {
                "id": pl.company_id.id,
                "name": noneify(pl.company_id.name),
            } or None,
            "country_groups": [
                {"id": g.id, "name": noneify(g.name)}
                for g in pl.country_group_ids
            ],
            "items_count": len(pl.item_ids),
        }
        if with_items:
            data["items"] = [
                self._serialize_item_full(it, env=env)
                for it in pl.item_ids
                if self._is_item_valid_by_date(it, request_date)
            ]
        return data

    @http.route([
        '/sales_rep_manager/<string:api_version>/pricelists',
        '/sales_rep_manager/<string:api_version>/pricelists/<int:pl_id>',
    ], type='http', auth='none', methods=['GET', 'OPTIONS'], csrf=False, cors='*')
    @jwt_required()
    def pricelists(self, pl_id=None, **kwargs):

        pre = self._preflight()
        if pre:
            return pre

        try:
            env = kwargs["_jwt_env"]

            # ----------------------------
            # Request date logic (NEW)
            # ----------------------------
            date_str = request.params.get("date")
            if date_str:
                request_date = datetime.strptime(date_str, "%Y-%m-%d")
            else:
                request_date = datetime.today()

            active_test = str(request.params.get('active_test', '1')).lower() not in ('0', 'false', 'no')
            Pricelist = env['product.pricelist'].with_context(
                dict(env.context, active_test=active_test)
            ).sudo()

            if pl_id:
                pl = Pricelist.browse(int(pl_id))
                if not pl.exists():
                    return format_response(False, "Pricelist not found", error_code=-404, http_status=404)

                data = self._serialize_pricelist_full(pl, env=env, request_date=request_date)
                return format_response(True, "Pricelist fetched successfully", data, http_status=200)

            domain = []

            if 'active' in request.params:
                is_active = str(request.params.get('active')).lower() in ('1', 'true', 't', 'yes', 'y')
                domain.append(('active', '=', is_active))

            company_id = request.params.get('company_id')
            if company_id:
                if str(company_id).lower() == 'false':
                    domain.append(('company_id', '=', False))
                else:
                    try:
                        domain.append(('company_id', 'in', [int(company_id), False]))
                    except Exception:
                        pass

            q = request.params.get('q')
            if q:
                domain.append(('name', 'ilike', q))

            try:
                limit = int(request.params.get('limit', 80))
            except Exception:
                limit = 80
            try:
                offset = int(request.params.get('offset', 0))
            except Exception:
                offset = 0

            order = request.params.get('order', 'sequence, id, name')
            compact = str(request.params.get('compact', '0')).lower() in ('1', 'true', 't', 'yes', 'y')

            total = Pricelist.search_count(domain)
            pls = Pricelist.search(domain, limit=limit, offset=offset, order=order)

            if compact:
                results = [
                    self._serialize_pricelist_brief(pl, with_items=False, env=env, request_date=request_date)
                    for pl in pls
                ]
            else:
                results = [
                    self._serialize_pricelist_full(pl, env=env, request_date=request_date)
                    for pl in pls
                ]

            return format_response(True, "Pricelists fetched successfully", {
                "total": total,
                "count": len(pls),
                "limit": limit,
                "offset": offset,
                "results": results
            }, http_status=200)

        except Exception as e:
            _logger.exception("Error fetching pricelists")
            return format_response(False, f"Internal error: {str(e)}", error_code=-500, http_status=500)

