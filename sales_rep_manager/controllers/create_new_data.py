# -*- coding: utf-8 -*-
# Done+++++++++++++++++++++++++++++++

import logging
import json
from datetime import datetime

from odoo import http
from odoo.http import request
from .api_utils import json_response, jwt_required, format_response, noneify

_logger = logging.getLogger(__name__)


class CreateNewData(http.Controller):

    # ----------------------------------------------------------------------
    # Helpers
    # ----------------------------------------------------------------------
    def _get_body(self):
        try:
            data = request.get_json_data() or {}
            if not isinstance(data, dict):
                return None, "Invalid JSON: body must be an object"
            return data, None
        except Exception:
            return None, "Invalid JSON body"

    # ----------------------------------------------------------------------
    # Create Sale Order
    # ----------------------------------------------------------------------
    @http.route(
        '/sales_rep_manager/<string:api_version>/create_sale_order',
        type='http', auth='none', methods=['POST', 'OPTIONS'], csrf=False, cors="*"
    )
    @jwt_required()
    def create_sale_order(self, **kwargs):
        if request.httprequest.method == 'OPTIONS':
            return json_response({"ok": True}, status=200)

        try:
            import json, base64
            from datetime import datetime

            env = kwargs["_jwt_env"]
            current_user = env['res.users'].browse(kwargs["_jwt_user_id"])

            data, error = self._get_body()
            if error:
                return format_response(False, error, error_code=-100, http_status=400)

            mobile_invoice_number = data.get('mobile_invoice_number') or data.get('mobile_local_number') or data.get(
                'mobile_number')
            partner_id = data.get('partner_id')
            items = data.get('items') or data.get('order_lines')

            # ===================== ✅ جديد: مرفقات متعددة =====================
            attachments_raw = data.get('attachments') or []
            attachment_base64_legacy = data.get('attachment_base64')
            attachment_name_legacy = data.get('attachment_name')

            # توافق مع الطريقة القديمة (صورة وحدة)
            if not attachments_raw and attachment_base64_legacy:
                attachments_raw = [{
                    'name': attachment_name_legacy or f"attachment_{datetime.utcnow().strftime('%Y%m%d%H%M%S')}",
                    'base64': attachment_base64_legacy,
                    'mimetype': data.get('attachment_mimetype') or 'image/jpeg',
                }]

            if not isinstance(attachments_raw, list):
                return format_response(
                    False,
                    "'attachments' must be a list",
                    error_code=-170,
                    http_status=400
                )

            MAX_ATTACHMENTS = 10
            if len(attachments_raw) > MAX_ATTACHMENTS:
                return format_response(
                    False,
                    f"Too many attachments. Maximum allowed is {MAX_ATTACHMENTS}",
                    error_code=-171,
                    http_status=400
                )

            for idx, att in enumerate(attachments_raw, start=1):
                if not isinstance(att, dict):
                    return format_response(
                        False,
                        f"Attachment #{idx}: must be an object with 'base64' field",
                        error_code=-172,
                        http_status=400
                    )
                if not att.get('base64'):
                    return format_response(
                        False,
                        f"Attachment #{idx}: missing 'base64' data",
                        error_code=-173,
                        http_status=400
                    )
                try:
                    base64.b64decode(att['base64'], validate=True)
                except Exception:
                    return format_response(
                        False,
                        f"Attachment #{idx}: invalid base64 encoding",
                        error_code=-174,
                        http_status=400
                    )
            # ==================================================================

            requested_status_raw = (data.get('order_status') or data.get('status') or data.get('state') or '').strip()
            status_map = {
                'confirmed': 'confirmed', 'confirm': 'confirmed', 'sale': 'confirmed',
                'طلب مؤكد': 'confirmed', 'مؤكد': 'confirmed',
                'invoiced': 'delivered_only', 'invoice': 'delivered_only', 'billed': 'delivered_only',
                'طلب مفوتر': 'delivered_only', 'مفوتر': 'delivered_only',
            }
            requested_status = status_map.get(requested_status_raw.lower(), None)

            if not partner_id:
                return format_response(False, "Missing required parameter: partner_id", error_code=-101,
                                       http_status=400)
            if not items or not isinstance(items, list):
                return format_response(False, "Missing or invalid 'items': must be a non-empty list", error_code=-102,
                                       http_status=400)

            # -------- مستودع من موقع المندوب --------
            RepProfile = env['sales.rep.profile'].sudo()
            rep_profile = RepProfile.search([('user_id', '=', current_user.id)], limit=1)
            if not rep_profile or not rep_profile.location_id:
                return format_response(False, "No location assigned to this sales representative", error_code=-404,
                                       http_status=200)

            rep_loc = rep_profile.location_id
            Warehouse = env['stock.warehouse'].sudo()
            wh = Warehouse.search([('view_location_id', 'parent_of', rep_loc.id)], limit=1) \
                 or Warehouse.search([('lot_stock_id', 'parent_of', rep_loc.id)], limit=1)
            wh = wh[:1]
            if not wh:
                return format_response(False, "Could not resolve a Warehouse for the rep location", error_code=-405,
                                       http_status=200)

            Product = env['product.product'].sudo()
            UoM = env['uom.uom'].sudo()
            SaleOrder = env['sale.order'].sudo()
            Attachment = env['ir.attachment'].sudo()

            order_lines_vals = []
            for idx, it in enumerate(items, start=1):
                pid = it.get('product_id')
                qty = it.get('quantity')
                price_unit = it.get('price_unit')
                discount = it.get('discount')
                name = it.get('name')
                product_uom_id = it.get('product_uom') or it.get('product_uom_id')

                if not pid:
                    return format_response(False, f"Item #{idx}: missing product_id", error_code=-110, http_status=400)
                if qty is None:
                    return format_response(False, f"Item #{idx}: missing quantity", error_code=-111, http_status=400)
                try:
                    qty = float(qty)
                except Exception:
                    return format_response(False, f"Item #{idx}: quantity must be a number", error_code=-112,
                                           http_status=400)
                if qty <= 0:
                    return format_response(False, f"Item #{idx}: quantity must be > 0", error_code=-113,
                                           http_status=400)

                product = Product.browse(int(pid))
                if not product.exists():
                    return format_response(False, f"Item #{idx}: product_id {pid} not found", error_code=-114,
                                           http_status=400)

                if price_unit is None:
                    price_unit = product.lst_price
                else:
                    try:
                        price_unit = float(price_unit)
                        if price_unit < 0:
                            return format_response(False, f"Item #{idx}: price_unit must be >= 0", error_code=-115,
                                                   http_status=400)
                    except Exception:
                        return format_response(False, f"Item #{idx}: price_unit must be a number", error_code=-116,
                                               http_status=400)

                if discount is not None:
                    try:
                        discount = float(discount)
                        if discount < 0 or discount > 100:
                            return format_response(False, f"Item #{idx}: discount must be between 0 and 100",
                                                   error_code=-117, http_status=400)
                    except Exception:
                        return format_response(False, f"Item #{idx}: discount must be a number", error_code=-118,
                                               http_status=400)

                uom_id = False
                if product_uom_id:
                    uom = UoM.browse(int(product_uom_id))
                    if not uom.exists():
                        return format_response(False, f"Item #{idx}: product_uom {product_uom_id} not found",
                                               error_code=-119, http_status=400)
                    uom_id = uom.id

                line_vals = {
                    'product_id': product.id,
                    'product_uom_qty': qty,
                    'price_unit': price_unit,
                }
                if name:
                    line_vals['name'] = name
                if discount is not None:
                    line_vals['discount'] = discount
                if uom_id:
                    line_vals['product_uom'] = uom_id

                order_lines_vals.append((0, 0, line_vals))

            sale_order = SaleOrder.create({
                'partner_id': partner_id,
                'user_id': current_user.id,
                'warehouse_id': wh.id,
                'order_line': order_lines_vals,
            })

            # ===================== ✅ جديد: حفظ جميع المرفقات =====================
            saved_attachments = []
            MIMETYPE_MAP = {
                'jpg': 'image/jpeg',
                'jpeg': 'image/jpeg',
                'png': 'image/png',
                'gif': 'image/gif',
                'webp': 'image/webp',
                'pdf': 'application/pdf',
                'bmp': 'image/bmp',
            }

            for idx, att in enumerate(attachments_raw, start=1):
                att_base64 = att.get('base64')
                att_name = (att.get('name') or '').strip()
                att_mimetype = (att.get('mimetype') or att.get('type') or '').strip()

                if not att_name:
                    att_name = f"attachment_{sale_order.id}_{idx}_{datetime.utcnow().strftime('%Y%m%d%H%M%S')}"

                if not att_mimetype:
                    ext = att_name.rsplit('.', 1)[-1].lower() if '.' in att_name else ''
                    att_mimetype = MIMETYPE_MAP.get(ext, 'image/jpeg')

                attachment = Attachment.create({
                    'name': att_name,
                    'type': 'binary',
                    'datas': att_base64,
                    'res_model': 'sale.order',
                    'res_id': sale_order.id,
                    'mimetype': att_mimetype,
                })

                saved_attachments.append({
                    'id': attachment.id,
                    'name': attachment.name,
                    'mimetype': att_mimetype,
                    'index': idx,
                })
            # =====================================================================

            # =========================
            # حفظ نتائج الـ MSL (اختياري)
            # =========================
            msl_results = data.get('msl_results') or []
            saved_msl = 0
            msl_saved_via = None
            if isinstance(msl_results, list) and msl_results:
                try:
                    if 'sale.order.msl.line' in env:
                        MSL = env['sale.order.msl.line'].sudo()
                        vals_list = []
                        for r in msl_results:
                            raw = str(r.get('status', 'unavailable')).strip().lower()
                            status = 'available' if raw in ('available', 'متوفر', '1', 'true', 'yes') else 'unavailable'
                            vals = {'order_id': sale_order.id, 'status': status}
                            pid = r.get('product_id')
                            cid = r.get('categ_id') or r.get('category_id')
                            if pid:
                                try:
                                    vals['product_id'] = int(pid)
                                except Exception:
                                    pass
                            if cid:
                                try:
                                    vals['categ_id'] = int(cid)
                                except Exception:
                                    pass
                            if 'product_id' in vals or 'categ_id' in vals:
                                vals_list.append(vals)
                        if vals_list:
                            MSL.create(vals_list)
                            saved_msl = len(vals_list)
                            msl_saved_via = 'model'
                    else:
                        Attachment.create({
                            'name': f"msl_results_{sale_order.name or sale_order.id}.json",
                            'type': 'binary',
                            'datas': base64.b64encode(
                                json.dumps(msl_results, ensure_ascii=False).encode('utf-8')).decode('utf-8'),
                            'res_model': 'sale.order',
                            'res_id': sale_order.id,
                            'mimetype': 'application/json',
                        })
                        saved_msl = len(msl_results)
                        msl_saved_via = 'attachment'
                except Exception:
                    pass

            # -------- سير العمل --------
            def _ensure_confirmed(order):
                if order.state not in ('sale', 'done'):
                    order.action_confirm()
                return order.state in ('sale', 'done')

            def _force_picking_from_rep_location(picking, rep_location, warehouse):
                try:
                    if warehouse and warehouse.out_type_id and picking.picking_type_id.id != warehouse.out_type_id.id:
                        picking.write({'picking_type_id': warehouse.out_type_id.id})
                except Exception:
                    pass
                if picking.location_id.id != rep_location.id:
                    picking.write({'location_id': rep_location.id})
                for mv in picking.move_ids_without_package:
                    if mv.location_id.id != rep_location.id:
                        mv.write({'location_id': rep_location.id})
                for ml in picking.move_line_ids:
                    if getattr(ml, 'location_id', False) and ml.location_id.id != rep_location.id:
                        ml.write({'location_id': rep_location.id})

            def _apply_rep_outgoing_type(picking, rep_profile, rep_location, warehouse):
                rep_pt = getattr(rep_profile, 'operation_type_id', False)
                rep_pt_is_out = bool(rep_pt and getattr(rep_pt, 'code', '') == 'outgoing')
                if rep_pt_is_out:
                    try:
                        if picking.picking_type_id.id != rep_pt.id:
                            picking.write({'picking_type_id': rep_pt.id})
                    except Exception:
                        pass
                    if rep_location and picking.location_id.id != rep_location.id:
                        picking.write({'location_id': rep_location.id})
                    try:
                        for mv in picking.move_ids_without_package:
                            if mv.location_id.id != rep_location.id:
                                mv.write({'location_id': rep_location.id})
                        for ml in picking.move_line_ids:
                            if getattr(ml, 'location_id', False) and ml.location_id.id != rep_location.id:
                                ml.write({'location_id': rep_location.id})
                    except Exception:
                        pass
                else:
                    _force_picking_from_rep_location(picking, rep_location, warehouse)

            def _deliver_all_pickings_from_rep(order, rep_location, warehouse):
                delivered = []
                try:
                    order.action_view_delivery()
                except Exception:
                    pass
                pickings = order.picking_ids.sudo().filtered(lambda p: p.picking_type_code == 'outgoing')
                for p in pickings:
                    if p.state in ('done', 'cancel'):
                        continue
                    if p.state == 'draft':
                        p.action_confirm()

                    _apply_rep_outgoing_type(p, rep_profile, rep_location, warehouse)

                    try:
                        p.action_assign()
                    except Exception:
                        pass
                    if p.move_line_ids:
                        for ml in p.move_line_ids:
                            if (getattr(ml, 'quantity', 0.0) or 0.0) <= 0.0:
                                ml.quantity = ml.product_uom_qty or ml.reserved_uom_qty or 0.0
                    else:
                        for mv in p.move_ids_without_package:
                            if (getattr(mv, 'quantity', 0.0) or 0.0) <= 0.0:
                                mv.quantity = mv.product_uom_qty
                    if hasattr(p, 'immediate_transfer'):
                        p.immediate_transfer = True
                    res = p.button_validate()
                    if isinstance(res, dict) and res.get('res_model') == 'stock.backorder.confirmation':
                        wiz = env['stock.backorder.confirmation'].sudo().browse(res.get('res_id', 0))
                        if not wiz or not wiz.exists():
                            wiz = env['stock.backorder.confirmation'].sudo().create({'pick_ids': [(4, p.id)]})
                        wiz.process()
                    if p.state == 'done':
                        delivered.append(p.id)
                return delivered

            workflow = {
                "requested_status": noneify(requested_status_raw) or None,
                "normalized_status": noneify(requested_status) or None,
                "confirmed": False,
                "delivered_picking_ids": [],
                "invoices_created": 0,
                "invoice_ids": [],
                "warehouse_id": wh.id,
                "warehouse_name": noneify(wh.name),
                "rep_location_id": rep_loc.id,
                "rep_location_name": noneify(rep_loc.complete_name or rep_loc.display_name or rep_loc.name),
                "msl_results_saved": int(saved_msl),
                "msl_saved_via": noneify(msl_saved_via),
            }

            if requested_status == 'confirmed':
                workflow["confirmed"] = _ensure_confirmed(sale_order)

            elif requested_status == 'delivered_only':
                workflow["confirmed"] = _ensure_confirmed(sale_order)
                workflow["delivered_picking_ids"] = _deliver_all_pickings_from_rep(sale_order, rep_loc, wh)

            # ---------- Serialization ----------
            lines_out = []
            for l in sale_order.order_line:
                lines_out.append({
                    "line_id": l.id,
                    "product_id": l.product_id.id,
                    "product_name": noneify(l.product_id.display_name),
                    "quantity": l.product_uom_qty,
                    "uom": noneify(l.product_uom.display_name if l.product_uom else None),
                    "price_unit": l.price_unit,
                    "discount": l.discount,
                    "subtotal": l.price_subtotal,
                    "tax": l.price_tax,
                    "total": l.price_total,
                })

            response_data = {
                "order_id": sale_order.id,
                "order_name": noneify(sale_order.name),
                "state": noneify(sale_order.state),
                "invoice_status": noneify(sale_order.invoice_status),
                "workflow": workflow,
                "currency": noneify(sale_order.currency_id.name),
                "amount_untaxed": sale_order.amount_untaxed,
                "amount_tax": sale_order.amount_tax,
                "amount_total": sale_order.amount_total,
                "line_count": len(lines_out),
                "lines": lines_out,
                # ✅ جديد: المرفقات
                "attachments": {
                    "total": len(saved_attachments),
                    "items": saved_attachments,
                },
                "invoices": None,
                "note": "Invoicing is disabled in this endpoint. The order was confirmed and (optionally) delivered only."
                if requested_status == 'delivered_only' else None,
            }

            return format_response(True, "Sale order created successfully", response_data, http_status=200)

        except Exception as e:
            _logger.exception("Error while creating sale order")
            return format_response(False, f"Internal error: {str(e)}", error_code=-500, http_status=500)

    # ----------------------------------------------------------------------
    # Create Customer
    # ----------------------------------------------------------------------
    @http.route(
        '/sales_rep_manager/<string:api_version>/create_customer',
        type='http', auth='none', methods=['POST', 'OPTIONS'], csrf=False, cors="*"
    )
    @jwt_required()
    def create_customer(self, **kwargs):
        if request.httprequest.method == 'OPTIONS':
            return json_response({"ok": True}, status=200)

        try:
            env = kwargs["_jwt_env"]
            current_user = env['res.users'].browse(kwargs["_jwt_user_id"])

            data, error = self._get_body()
            if error:
                return format_response(False, error, error_code=-100, http_status=400)

            name = (data.get('name') or '').strip()
            email = (data.get('email') or '').strip()
            phone = (data.get('phone') or '').strip()
            customer_classification = data.get('customer_classification')

            street = (data.get('street') or data.get('address') or '').strip()
            city = (data.get('city') or '').strip()

            # ===================== ✅ جديد: area_id =====================
            area_id = data.get('area_id')
            # =============================================================

            # -----------------------------
            # latitude / longitude from mobile
            # -----------------------------
            raw_lat = data.get('latitude', data.get('partner_latitude'))
            raw_lng = data.get('longitude', data.get('partner_longitude'))
            partner_latitude = None
            partner_longitude = None

            if raw_lat not in (None, '') and raw_lng not in (None, ''):
                try:
                    partner_latitude = float(raw_lat)
                    partner_longitude = float(raw_lng)
                except (ValueError, TypeError):
                    return format_response(
                        False,
                        "Invalid latitude/longitude format",
                        error_code=-150,
                        http_status=400,
                    )

            country_id = data.get('country_id')
            country_code = data.get('country_code')
            state_id = data.get('state_id')
            state_code = data.get('state_code')
            state_name = data.get('state_name')

            industry_id = data.get('industry_id')

            if not name:
                return format_response(False, "Customer name is required", error_code=-101, http_status=400)

            Country = env['res.country'].sudo()
            State = env['res.country.state'].sudo()
            Industry = env['res.partner.industry'].sudo()
            Partner = env['res.partner'].sudo()
            RepProfile = env['sales.rep.profile'].sudo()
            # ===================== ✅ جديد: City Model =====================
            CityModel = env['res.city'].sudo()
            # ================================================================

            resolved_country = None
            resolved_state = None
            resolved_industry = None
            # ===================== ✅ جديد =====================
            resolved_area = None
            # ====================================================

            if not country_id and not country_code:
                resolved_country = env.ref('base.sy', raise_if_not_found=False)

            # --------------------------------------------------
            # Resolve country
            # --------------------------------------------------
            if country_id:
                c = Country.browse(int(country_id))
                if not c.exists():
                    return format_response(False, f"country_id {country_id} not found", error_code=-121,
                                           http_status=400)
                resolved_country = c
            elif country_code:
                c = Country.search([('code', '=', str(country_code).upper())], limit=1)
                if not c:
                    return format_response(False, f"country_code '{country_code}' not found", error_code=-122,
                                           http_status=400)
                resolved_country = c

            # Default country to Syria if no country but state* fields are provided
            if not resolved_country and (state_id or state_code or state_name):
                try:
                    resolved_country = env.ref('base.sy', raise_if_not_found=False)
                except Exception:
                    resolved_country = None

            # --------------------------------------------------
            # Resolve state
            # --------------------------------------------------
            if state_id:
                s = State.browse(int(state_id))
                if not s.exists():
                    return format_response(False, f"state_id {state_id} not found", error_code=-130, http_status=400)
                resolved_state = s
                if resolved_country and s.country_id and s.country_id.id != resolved_country.id:
                    return format_response(False, "state_id does not belong to provided country", error_code=-131,
                                           http_status=400)
                if not resolved_country and s.country_id:
                    resolved_country = s.country_id
            elif state_code or state_name:
                domain = []
                if resolved_country:
                    domain.append(('country_id', '=', resolved_country.id))
                s = None
                if state_code:
                    domain_code = domain + [('code', '=', str(state_code).upper())]
                    s = State.search(domain_code, limit=1) or (
                        None if resolved_country else State.search([('code', '=', str(state_code).upper())], limit=1)
                    )
                if not s and state_name:
                    domain_name = domain + ['|', ('name', '=ilike', state_name), ('name', 'ilike', state_name)]
                    s = State.search(domain_name, limit=1)
                if not s:
                    return format_response(False, "State not found with provided state_code/state_name",
                                           error_code=-132, http_status=400)
                resolved_state = s
                if not resolved_country and s.country_id:
                    resolved_country = s.country_id

            # --------------------------------------------------
            # ✅ جديد: Resolve area (res.city)
            # --------------------------------------------------
            if area_id:
                try:
                    area_id = int(area_id)
                except (ValueError, TypeError):
                    return format_response(
                        False,
                        "Invalid area_id, must be an integer",
                        error_code=-160,
                        http_status=400
                    )

                area = CityModel.browse(area_id)
                if not area.exists():
                    return format_response(
                        False,
                        f"area_id {area_id} not found",
                        error_code=-161,
                        http_status=400
                    )

                resolved_area = area

                # التحقق من تطابق المنطقة مع المحافظة المختارة
                if resolved_state and area.state_id and area.state_id.id != resolved_state.id:
                    return format_response(
                        False,
                        "Selected area does not belong to the provided state/governorate",
                        error_code=-162,
                        http_status=400
                    )

                # إذا لم يُرسل state_id، نأخذه تلقائياً من المنطقة
                if not resolved_state and area.state_id:
                    resolved_state = area.state_id

                # إذا لم يُرسل country_id، نأخذه تلقائياً من المنطقة
                if not resolved_country and area.country_id:
                    resolved_country = area.country_id

                # إذا لم يُرسل city text، نأخذ اسم المنطقة
                if not city:
                    city = area.name
            # --------------------------------------------------

            # --------------------------------------------------
            # Resolve industry
            # --------------------------------------------------
            if industry_id:
                ind = Industry.browse(int(industry_id))
                if not ind.exists():
                    return format_response(False, f"industry_id {industry_id} not found", error_code=-140,
                                           http_status=400)
                resolved_industry = ind

            # --------------------------------------------------
            # Route / area constraint
            # --------------------------------------------------
            rep_profile = RepProfile.search([('user_id', '=', current_user.id)], limit=1)
            allowed_states = rep_profile.route_id.area_ids if (rep_profile and rep_profile.route_id) else State.browse()

            if allowed_states:
                allowed_ids = set(allowed_states.ids)

                if resolved_state:
                    if resolved_state.id not in allowed_ids:
                        return format_response(
                            False,
                            "Selected state is not allowed for this sales route",
                            error_code=-133,
                            http_status=400,
                        )
                else:
                    if len(allowed_states) == 1:
                        resolved_state = allowed_states[0]
                        if not resolved_country and resolved_state.country_id:
                            resolved_country = resolved_state.country_id

            # --------------------------------------------------
            # Create partner
            # --------------------------------------------------
            vals = {
                'name': name,
                'customer_classification': customer_classification,
                'customer_rank': 1,
                'company_id': current_user.company_id.id,
            }
            if email:
                vals['email'] = email
            if phone:
                vals['phone'] = phone
            if street:
                vals['street'] = street
            if city:
                vals['city'] = city
            if resolved_country:
                vals['country_id'] = resolved_country.id
            if resolved_state:
                vals['state_id'] = resolved_state.id
            if resolved_industry:
                vals['industry_id'] = resolved_industry.id

            if partner_latitude is not None and partner_longitude is not None:
                vals['partner_latitude'] = partner_latitude
                vals['partner_longitude'] = partner_longitude

            # ===================== ✅ جديد: حفظ area_id =====================
            if resolved_area:
                vals['city_id'] = resolved_area.id  # حقل res.city في res.partner
            # =================================================================

            partner = Partner.create(vals)

            response_data = {
                "customer_id": partner.id,
                "name": noneify(partner.name),
                "email": noneify(partner.email),
                "phone": noneify(partner.phone),
                "customer_classification": noneify(getattr(partner, 'customer_classification', None)),
                "street": noneify(partner.street),
                "city": noneify(partner.city),
                "partner_latitude": noneify(getattr(partner, 'partner_latitude', None)),
                "partner_longitude": noneify(getattr(partner, 'partner_longitude', None)),
                "country": ({
                                "id": partner.country_id.id,
                                "name": noneify(partner.country_id.name),
                                "code": noneify(partner.country_id.code),
                            } if partner.country_id else None),
                "state": ({
                              "id": partner.state_id.id,
                              "name": noneify(partner.state_id.name),
                              "code": noneify(partner.state_id.code),
                          } if partner.state_id else None),
                # ===================== ✅ جديد: area في الاستجابة =====================
                "area": ({
                             "id": partner.city_id.id,
                             "name": noneify(partner.city_id.name),
                             "zipcode": noneify(getattr(partner.city_id, 'zipcode', None)),
                         } if partner.city_id else None),
                # ======================================================================
                "industry": ({
                                 "id": partner.industry_id.id,
                                 "name": noneify(partner.industry_id.name),
                                 "full_name": noneify(partner.industry_id.full_name),
                             } if partner.industry_id else None),
                "company": ({
                                "id": partner.company_id.id,
                                "name": noneify(partner.company_id.name),
                            } if partner.company_id else None),
            }

            return format_response(True, "Customer created successfully", response_data, http_status=200)

        except Exception as e:
            _logger.exception("Error while creating customer")
            return format_response(False, f"Internal error: {str(e)}", error_code=-500, http_status=500)

    @http.route(
        '/sales_rep_manager/<string:api_version>/update_customer',
        type='http', auth='none', methods=['POST', 'OPTIONS'], csrf=False, cors="*"
    )
    @jwt_required()
    def update_customer(self, **kwargs):
        if request.httprequest.method == 'OPTIONS':
            return json_response({"ok": True}, status=200)

        try:
            env = kwargs["_jwt_env"]
            current_user = env['res.users'].browse(kwargs["_jwt_user_id"])

            data, error = self._get_body()
            if error:
                return format_response(False, error, error_code=-100, http_status=400)

            # --------------------------------------------------
            # Identify customer
            # --------------------------------------------------
            customer_id = data.get('customer_id') or data.get('partner_id')
            if not customer_id:
                return format_response(False, "customer_id (or partner_id) is required", error_code=-101,
                                       http_status=400)

            Partner = env['res.partner'].sudo()
            Country = env['res.country'].sudo()
            State = env['res.country.state'].sudo()
            Industry = env['res.partner.industry'].sudo()
            RepProfile = env['sales.rep.profile'].sudo()

            try:
                customer_id_int = int(customer_id)
            except (TypeError, ValueError):
                return format_response(False, "customer_id must be integer", error_code=-102, http_status=400)

            partner = Partner.browse(customer_id_int)
            if not partner.exists():
                return format_response(False, f"Customer {customer_id} not found", error_code=-103, http_status=404)

            # Optional: restrict to same company as current user
            if partner.company_id and partner.company_id.id != current_user.company_id.id:
                return format_response(False, "Access denied for this customer", error_code=-104, http_status=403)

            # --------------------------------------------------
            # Basic fields (only update if key present)
            # --------------------------------------------------
            vals = {}

            if 'name' in data:
                vals['name'] = data.get('name') or False
            if 'email' in data:
                vals['email'] = data.get('email') or False
            if 'phone' in data:
                vals['phone'] = data.get('phone') or False
            if 'customer_classification' in data:
                vals['customer_classification'] = data.get('customer_classification') or False

            # address
            if 'street' in data or 'address' in data:
                street = (data.get('street') or data.get('address') or '').strip()
                vals['street'] = street or False
            if 'city' in data:
                city = (data.get('city') or '').strip()
                vals['city'] = city or False

            # --------------------------------------------------
            # Geo coordinates (mobile)
            # Accept latitude/longitude OR partner_latitude/partner_longitude
            # --------------------------------------------------
            raw_lat = data.get('latitude', data.get('partner_latitude'))
            raw_lng = data.get('longitude', data.get('partner_longitude'))

            # Only touch if provided
            if raw_lat not in (None, '') or raw_lng not in (None, ''):
                # both must be present
                if raw_lat in (None, '') or raw_lng in (None, ''):
                    return format_response(
                        False,
                        "Both latitude and longitude must be provided",
                        error_code=-150,
                        http_status=400,
                    )
                try:
                    vals['partner_latitude'] = float(raw_lat)
                    vals['partner_longitude'] = float(raw_lng)
                except (ValueError, TypeError):
                    return format_response(
                        False,
                        "Invalid latitude/longitude format",
                        error_code=-151,
                        http_status=400,
                    )

            # --------------------------------------------------
            # Country / State / Industry resolution (optional)
            # Only run if some keys are present in payload
            # --------------------------------------------------
            country_id = data.get('country_id') if 'country_id' in data else None
            country_code = data.get('country_code') if 'country_code' in data else None
            state_id = data.get('state_id') if 'state_id' in data else None
            state_code = data.get('state_code') if 'state_code' in data else None
            state_name = data.get('state_name') if 'state_name' in data else None
            industry_id = data.get('industry_id') if 'industry_id' in data else None

            resolved_country = partner.country_id
            resolved_state = partner.state_id
            resolved_industry = partner.industry_id

            # country
            if country_id is not None or country_code is not None:
                resolved_country = None
                if country_id:
                    c = Country.browse(int(country_id))
                    if not c.exists():
                        return format_response(False, f"country_id {country_id} not found", error_code=-121,
                                               http_status=400)
                    resolved_country = c
                elif country_code:
                    c = Country.search([('code', '=', str(country_code).upper())], limit=1)
                    if not c:
                        return format_response(False, f"country_code '{country_code}' not found", error_code=-122,
                                               http_status=400)
                    resolved_country = c

            # state
            if state_id is not None or state_code is not None or state_name is not None:
                resolved_state = None
                if state_id:
                    s = State.browse(int(state_id))
                    if not s.exists():
                        return format_response(False, f"state_id {state_id} not found", error_code=-130,
                                               http_status=400)
                    resolved_state = s
                elif state_code or state_name:
                    domain = []
                    if resolved_country:
                        domain.append(('country_id', '=', resolved_country.id))
                    s = None
                    if state_code:
                        domain_code = domain + [('code', '=', str(state_code).upper())]
                        s = State.search(domain_code, limit=1) or (
                            None if resolved_country else State.search([('code', '=', str(state_code).upper())],
                                                                       limit=1)
                        )
                    if not s and state_name:
                        domain_name = domain + ['|', ('name', '=ilike', state_name), ('name', 'ilike', state_name)]
                        s = State.search(domain_name, limit=1)
                    if not s:
                        return format_response(False, "State not found with provided state_code/state_name",
                                               error_code=-132, http_status=400)
                    resolved_state = s

            # industry
            if industry_id is not None:
                if industry_id:
                    ind = Industry.browse(int(industry_id))
                    if not ind.exists():
                        return format_response(False, f"industry_id {industry_id} not found", error_code=-140,
                                               http_status=400)
                    resolved_industry = ind
                else:
                    resolved_industry = False

            # --------------------------------------------------
            # Route / area constraint when state is being changed
            # --------------------------------------------------
            if (state_id is not None) or (state_code is not None) or (state_name is not None):
                rep_profile = RepProfile.search([('user_id', '=', current_user.id)], limit=1)
                allowed_states = rep_profile.route_id.area_ids if (
                        rep_profile and rep_profile.route_id) else State.browse()
                if allowed_states and resolved_state:
                    if resolved_state.id not in set(allowed_states.ids):
                        return format_response(
                            False,
                            "Selected state is not allowed for this sales route",
                            error_code=-133,
                            http_status=400,
                        )

            # write resolved country/state/industry into vals
            if (country_id is not None) or (country_code is not None):
                vals['country_id'] = resolved_country.id if resolved_country else False
            if (state_id is not None) or (state_code is not None) or (state_name is not None):
                vals['state_id'] = resolved_state.id if resolved_state else False
            if industry_id is not None:
                vals['industry_id'] = resolved_industry.id if resolved_industry else False

            # --------------------------------------------------
            # If nothing to update
            # --------------------------------------------------
            if not vals:
                # no-op but return current data
                updated_partner = partner
            else:
                partner.write(vals)
                updated_partner = partner

            # --------------------------------------------------
            # Build response
            # --------------------------------------------------
            response_data = {
                "customer_id": updated_partner.id,
                "name": noneify(updated_partner.name),
                "email": noneify(updated_partner.email),
                "phone": noneify(updated_partner.phone),
                "customer_classification": noneify(getattr(updated_partner, 'customer_classification', None)),
                "street": noneify(updated_partner.street),
                "city": noneify(updated_partner.city),
                "partner_latitude": noneify(getattr(updated_partner, 'partner_latitude', None)),
                "partner_longitude": noneify(getattr(updated_partner, 'partner_longitude', None)),
                "country": ({
                                "id": updated_partner.country_id.id,
                                "name": noneify(updated_partner.country_id.name),
                                "code": noneify(updated_partner.country_id.code),
                            } if updated_partner.country_id else None),
                "state": ({
                              "id": updated_partner.state_id.id,
                              "name": noneify(updated_partner.state_id.name),
                              "code": noneify(updated_partner.state_id.code),
                          } if updated_partner.state_id else None),
                "industry": ({
                                 "id": updated_partner.industry_id.id,
                                 "name": noneify(updated_partner.industry_id.name),
                                 "full_name": noneify(updated_partner.industry_id.full_name),
                             } if updated_partner.industry_id else None),
                "company": ({
                                "id": updated_partner.company_id.id,
                                "name": noneify(updated_partner.company_id.name),
                            } if updated_partner.company_id else None),
            }

            return format_response(True, "Customer updated successfully", response_data, http_status=200)

        except Exception as e:
            _logger.exception("Error while updating customer")
            return format_response(False, f"Internal error: {str(e)}", error_code=-500, http_status=500)
