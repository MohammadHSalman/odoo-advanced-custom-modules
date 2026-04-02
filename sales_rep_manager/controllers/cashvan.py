# -*- coding: utf-8 -*-
import logging

from odoo import http, SUPERUSER_ID, fields, api
from odoo.http import request
from .api_utils import format_response, json_response, jwt_required, noneify
from odoo.exceptions import UserError, ValidationError

_logger = logging.getLogger(__name__)


class CashVanAPI(http.Controller):

    def _log_cashvan_failure(
            self, env, user_id, partner_id, mobile_invoice_number,
            error_message, error_stage, payload_text
    ):
        cr = env.registry.cursor()
        try:
            log_env = api.Environment(cr, SUPERUSER_ID, {})
            log_env['cashvan.invoice.log'].create({
                'user_id': user_id,
                'partner_id': partner_id,
                'mobile_invoice_number': mobile_invoice_number,
                'error_message': error_message,
                'error_stage': error_stage or 'other',
                'payload': payload_text,
            })
            cr.commit()
        finally:
            cr.close()

    # -----------------------------
    # Helper: save MSL results on a sale order (fallback to JSON attachment)
    # -----------------------------
    def _save_msl_results(self, env, sale_order, msl_results):
        import json, base64

        if not sale_order or not msl_results or not isinstance(msl_results, list):
            return 0, None

        saved_msl = 0
        saved_via = None

        # تطبيع الإدخال إلى قائمة product_ids
        product_ids = []
        try:
            if all(isinstance(x, (int, str)) for x in msl_results):
                for x in msl_results:
                    try:
                        pid = int(str(x).strip())
                        if pid > 0:
                            product_ids.append(pid)
                    except Exception:
                        continue
            else:
                for r in msl_results:
                    if not isinstance(r, dict):
                        continue
                    pid = r.get('product_id')
                    if pid is None:
                        continue
                    try:
                        pid = int(pid)
                        if pid > 0:
                            product_ids.append(pid)
                    except Exception:
                        continue
        except Exception:
            pass

        product_ids = list(dict.fromkeys(product_ids))
        if not product_ids:
            return 0, None

        try:
            if 'sale.order.msl.line' in env:
                MSL = env['sale.order.msl.line'].sudo()
                existing = MSL.search([
                    ('order_id', '=', sale_order.id),
                    ('product_id', 'in', product_ids),
                ])
                if existing:
                    existing.write({'status': 'available'})

                existing_pids = set(existing.mapped('product_id').ids) if existing else set()
                to_create = [pid for pid in product_ids if pid not in existing_pids]
                if to_create:
                    MSL.create([
                        {
                            'order_id': sale_order.id,
                            'product_id': pid,
                            'status': 'available',
                        }
                        for pid in to_create
                    ])

                saved_msl = len(product_ids)
                saved_via = 'model'
            else:
                normalized = [{'product_id': pid, 'status': 'available'} for pid in product_ids]
                env['ir.attachment'].sudo().create({
                    'name': f"msl_results_{sale_order.name or sale_order.id}.json",
                    'type': 'binary',
                    'datas': base64.b64encode(
                        json.dumps(normalized, ensure_ascii=False).encode('utf-8')
                    ).decode('utf-8'),
                    'res_model': 'sale.order',
                    'res_id': sale_order.id,
                    'mimetype': 'application/json',
                })
                saved_msl = len(product_ids)
                saved_via = 'attachment'
        except Exception:
            pass

        return int(saved_msl), saved_via

    # -----------------------------
    # Helper: apply loyalty rewards coming from mobile (reward=True)
    # -----------------------------
    def _apply_mobile_rewards(self, env, sale_order, reward_items):
        if not sale_order or not reward_items:
            return

        if 'sale.loyalty.reward.wizard' not in env:
            _logger.info("Loyalty reward wizard model not found, skip mobile rewards.")
            return

        Product = env['product.product'].sudo()
        Wizard = env['sale.loyalty.reward.wizard'].sudo()

        try:
            sale_order._update_programs_and_rewards()
            claimable_rewards = sale_order._get_claimable_rewards() or {}
        except Exception as e:
            _logger.exception("Cannot compute claimable rewards for order %s: %s", sale_order.id, e)
            return

        if not claimable_rewards:
            _logger.info("No claimable rewards for order %s, skip mobile rewards.", sale_order.id)
            return

        for it in reward_items:
            product_id = it.get('product_id')
            if not product_id:
                continue

            try:
                product = Product.browse(int(product_id))
            except Exception:
                continue

            if not product or not product.exists():
                continue

            selected_reward = False

            # نبحث عن reward من نوع product ويحتوي هذا المنتج
            try:
                for coupon, rewards in claimable_rewards.items():
                    candidate = rewards.filtered(
                        lambda r: r.reward_type == 'product' and product in r.reward_product_ids
                    )
                    if candidate:
                        selected_reward = candidate[0]
                        break
            except Exception as e:
                _logger.exception("Error while searching reward for product %s: %s", product.id, e)
                continue

            if not selected_reward:
                _logger.info(
                    "No matching loyalty reward found for product %s on order %s.",
                    product.id, sale_order.id
                )
                continue

            wiz_ctx = dict(env.context, active_model='sale.order', active_id=sale_order.id)
            wizard_vals = {
                'order_id': sale_order.id,
                'selected_reward_id': selected_reward.id,
            }

            try:
                if getattr(selected_reward, 'multi_product', False):
                    wizard_vals['selected_product_id'] = product.id
            except Exception:
                pass

            try:
                wizard = Wizard.with_context(wiz_ctx).create(wizard_vals)
                wizard.action_apply()
                _logger.info(
                    "Applied mobile reward %s for product %s on order %s via wizard.",
                    selected_reward.id, product.id, sale_order.id
                )
            except Exception as e:
                _logger.exception(
                    "Error applying mobile reward %s for product %s on order %s: %s",
                    selected_reward.id, product.id, sale_order.id, e
                )
                continue

    # -----------------------------
    # Safe JSON body reader (type='http')
    # -----------------------------
    def _get_body(self):
        import json as _json
        try:
            if hasattr(request, "get_json_data"):
                try:
                    data = request.get_json_data()
                    if data is None:
                        return {}, None
                    if not isinstance(data, dict):
                        return None, "Invalid JSON: body must be an object"
                    return data, None
                except Exception:
                    pass

            if hasattr(request.httprequest, "json") and request.httprequest.json is not None:
                if not isinstance(request.httprequest.json, dict):
                    return None, "Invalid JSON: body must be an object"
                return request.httprequest.json, None

            raw = getattr(request.httprequest, "get_data", lambda: b"")() or getattr(
                request.httprequest, "data", b""
            )
            if not raw:
                return {}, None
            text = raw.decode("utf-8-sig")
            data = _json.loads(text)
            if not isinstance(data, dict):
                return None, "Invalid JSON: body must be an object"
            return data, None
        except Exception as e:
            return None, f"Invalid JSON body: {e}"

    # -----------------------------
    # Helpers: locate proper picking types (returns for incoming)
    # -----------------------------
    def _find_return_receipt_type(self, env, company):
        PickingType = env['stock.picking.type'].sudo()
        dom_base = [('code', '=', 'incoming')]
        if company:
            dom_base.append(('company_id', '=', company.id))

        pt = PickingType.search(dom_base + [('name', 'ilike', 'return')], limit=1)
        if pt:
            return pt

        pt = PickingType.search(dom_base, limit=1)
        if pt:
            return pt

        return PickingType.search([('code', '=', 'incoming')], limit=1)

    # -----------------------------
    # Helpers: damaged location
    # -----------------------------
    def _get_damaged_location(self, env, rep_location, company):
        Location = env['stock.location'].sudo()
        dmg = env.ref('stock.stock_location_scrapped', raise_if_not_found=False)
        if dmg:
            return dmg

        dmg = Location.search([
            ('name', '=', 'Damaged'),
            ('location_id', '=', rep_location.id),
        ], limit=1)
        if dmg:
            return dmg

        vals = {
            'name': 'Damaged',
            'usage': 'internal',
            'location_id': rep_location.id,
        }
        if company:
            vals['company_id'] = company.id
        return Location.create(vals)

    # -----------------------------
    # Helpers: stock pickings / quantities
    # -----------------------------
    def _force_outgoing_from_rep(self, env, picking, rep_location, warehouse):
        try:
            if warehouse and getattr(warehouse, 'out_type_id', False) and \
                    picking.picking_type_id.id != warehouse.out_type_id.id:
                picking.write({'picking_type_id': warehouse.out_type_id.id})
        except Exception:
            pass
        try:
            if rep_location and picking.location_id.id != rep_location.id:
                picking.write({'location_id': rep_location.id})
        except Exception:
            pass
        try:
            for mv in picking.move_ids_without_package:
                if mv.location_id.id != rep_location.id:
                    mv.write({'location_id': rep_location.id})
            for ml in picking.move_line_ids:
                if getattr(ml, 'location_id', False) and ml.location_id.id != rep_location.id:
                    ml.write({'location_id': rep_location.id})
        except Exception:
            pass

    def _apply_rep_outgoing_type(self, env, picking, rep_profile, rep_location, warehouse):
        rep_pt = getattr(rep_profile, 'operation_type_id', False)
        rep_pt_is_out = bool(rep_pt and getattr(rep_pt, 'code', '') == 'outgoing')

        if rep_pt_is_out:
            try:
                if picking.picking_type_id.id != rep_pt.id:
                    picking.write({'picking_type_id': rep_pt.id})
            except Exception:
                pass

            try:
                if rep_location and picking.location_id.id != rep_location.id:
                    picking.write({'location_id': rep_location.id})
            except Exception:
                pass

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
            self._force_outgoing_from_rep(env, picking, rep_location, warehouse)

    def _fill_done_quantities(self, picking):
        for mv in picking.move_ids_without_package:
            if not mv.move_line_ids:
                qty_target = (
                        getattr(mv, 'product_uom_qty', 0.0)
                        or getattr(mv, 'reserved_availability', 0.0)
                        or 0.0
                )
                if hasattr(mv, 'quantity_done'):
                    mv.quantity_done = qty_target
                elif hasattr(mv, 'quantity'):
                    mv.quantity = qty_target
                continue
            for ml in mv.move_line_ids:
                qty_target = (
                        getattr(ml, 'reserved_uom_qty', 0.0)
                        or getattr(mv, 'product_uom_qty', 0.0)
                        or getattr(ml, 'qty_done', 0.0)
                        or 0.0
                )
                if hasattr(ml, 'qty_done'):
                    ml.qty_done = qty_target
                elif hasattr(ml, 'quantity_done'):
                    ml.quantity_done = qty_target
                elif hasattr(ml, 'quantity'):
                    ml.quantity = qty_target

    def _process_wizard(self, env, res_dict, model_name, pick_ids):
        if not (isinstance(res_dict, dict) and res_dict.get('res_model') == model_name):
            return
        wiz_id = res_dict.get('res_id', 0)
        wiz = env[model_name].sudo().browse(wiz_id)
        if not wiz or not wiz.exists():
            if model_name == 'stock.immediate.transfer':
                wiz = env['stock.immediate.transfer'].sudo().create({'pick_ids': [(6, 0, pick_ids)]})
            elif model_name == 'stock.backorder.confirmation':
                wiz = env['stock.backorder.confirmation'].sudo().create({'pick_ids': [(6, 0, pick_ids)]})
        wiz.process()

    def _validate_picking(self, env, picking):
        if picking.state == 'draft':
            picking.action_confirm()

        try:
            picking.action_assign()
        except Exception:
            pass

        try:
            if hasattr(picking, 'immediate_transfer'):
                picking.immediate_transfer = True
        except Exception:
            pass

        self._fill_done_quantities(picking)
        res = picking.with_user(SUPERUSER_ID).button_validate()

        self._process_wizard(env, res, 'stock.immediate.transfer', [picking.id])

        if picking.state not in ('done', 'cancel'):
            res2 = picking.with_user(SUPERUSER_ID).button_validate()
            self._process_wizard(env, res2, 'stock.backorder.confirmation', [picking.id])

        self._process_wizard(env, res, 'stock.backorder.confirmation', [picking.id])

        return picking.state == 'done'

    # -----------------------------
    # Helper: get rep cash journal for a given currency (single source of truth)
    # -----------------------------
    def _get_rep_journal_for_currency(self, env, rep_profile, currency_rec):
        """
        Always pick the cash journal whose currency == payment currency.
        If no mapping found, return False.
        """
        if not rep_profile or not currency_rec:
            return False

        # primary: use loaded journal_map_ids
        line = rep_profile.journal_map_ids.filtered(
            lambda l: l.currency_id.id == currency_rec.id
        )[:1]
        if line and line.journal_id:
            return line.journal_id

        # fallback: search mapping table
        if 'sales.rep.cash.journal.map' in env:
            Map = env['sales.rep.cash.journal.map'].sudo()
            mapping = Map.search([
                ('profile_id', '=', rep_profile.id),
                ('currency_id', '=', currency_rec.id),
            ], limit=1)
            if mapping and mapping.journal_id:
                return mapping.journal_id

        return False

    # -----------------------------
    # Helper: resolve currency (id / code / unit label / raw value) with fallback
    # -----------------------------
    def _resolve_currency(self, env, cur_value=None, cur_id=None, cur_code=None, fallback=None):
        Currency = env['res.currency'].sudo()

        if cur_value is not None:
            try:
                val_int = int(cur_value)
                cur = Currency.browse(val_int)
                if cur.exists():
                    return cur
            except Exception:
                cur = Currency.search([('name', '=', str(cur_value))], limit=1) \
                      or Currency.search([('currency_unit_label', '=', str(cur_value))], limit=1)
                if cur:
                    return cur

        if cur_id:
            cur = Currency.browse(int(cur_id))
            if cur.exists():
                return cur

        if cur_code:
            cur = Currency.search([('name', '=', cur_code)], limit=1) \
                  or Currency.search([('currency_unit_label', '=', cur_code)], limit=1)
            if cur:
                return cur

        return fallback

    # =============================
    # Public Endpoints
    # =============================

    @http.route(
        ['/sales_rep_manager/<string:api_version>/currencies'],
        type='http', auth='none', methods=['GET', 'OPTIONS'], csrf=False, cors='*'
    )
    @jwt_required()
    def get_active_currencies(self, **kwargs):
        if request.httprequest.method == 'OPTIONS':
            return json_response({"ok": True}, status=200)
        try:
            env = kwargs["_jwt_env"]
            Currency = env['res.currency'].sudo()
            currencies = Currency.search([('active', '=', True)], order='name asc')

            def pos_value(c):
                return 0 if (c.position or 'before') == 'before' else 1

            data = [{
                "id": c.id,
                "name": noneify(c.name),
                "is_use": c.is_use,
                "symbol": noneify(c.symbol),
                "rounding": c.rounding,
                "rounding_factor": c.rounding or 0.01,
                "decimal_places": getattr(c, 'decimal_places', 2),
                "position": noneify(c.position),
                "position_value": pos_value(c),
                "currency_unit_label": noneify(c.currency_unit_label),
                "currency_subunit_label": noneify(c.currency_subunit_label),
                "exchange_rate": c.rate,
                "SYP_per_Unit": c.inverse_rate,
            } for c in currencies]

            return format_response(True, "Active currencies", data, http_status=200)

        except Exception as e:
            _logger.exception("Error fetching currencies")
            return format_response(False, f"Internal error: {str(e)}", error_code=-500, http_status=500)

    # -----------------------------
    # CashVan: Create SO -> Deliver -> Invoice -> Pay (all-in-one)
    # -----------------------------
    # inside your existing function: ONLY add/replace the marked parts

    @http.route(
        ['/sales_rep_manager/<string:api_version>/cashvan/invoice'],
        type='http', auth='none', methods=['POST', 'OPTIONS'], csrf=False, cors='*'
    )
    @jwt_required()
    def cashvan_invoice(self, **kwargs):
        # 1. CORS Preflight
        if request.httprequest.method == 'OPTIONS':
            return json_response({"ok": True}, status=200)

        env = kwargs["_jwt_env"]
        current_user = env['res.users'].browse(kwargs["_jwt_user_id"])

        # استيراد المكتبات
        from odoo.exceptions import UserError, ValidationError
        import json
        import logging

        # تعريف اللوجر
        _logger = logging.getLogger(__name__)
        _logger.info(f">>>>>moh>>>> START: cashvan_invoice called by User ID: {current_user.id}")

        # ================= LOGGING VARS =================
        error_stage = 'other'
        payload_text = None
        partner_id = None
        mobile_invoice_number = None
        # ================================================

        try:
            from datetime import datetime, timedelta

            # قراءة البيانات
            _logger.info(">>>>>moh>>>> Reading request body...")
            body, error = self._get_body()
            if error:
                _logger.error(f">>>>>moh>>>> Body parsing error: {error}")
                error_stage = 'validation'
                return format_response(False, error, error_code=-100, http_status=400)

            try:
                payload_text = json.dumps(body, ensure_ascii=False)
            except:
                payload_text = str(body)

            partner_id = body.get('partner_id')
            items = body.get('items') or body.get('lines') or []
            mobile_invoice_number = body.get('mobile_invoice_number')
            # تعريف القائمة هنا لنستخدمها في التحقق
            payment_list = body.get('payment') or []

            _logger.info(
                f">>>>>moh>>>> Payload Parsed. Partner: {partner_id}, Mobile Ref: {mobile_invoice_number}, Items Count: {len(items)}")

            # ==================== (1) التحقق من التكرار (Idempotency Check) ====================
            error_stage = 'duplicate_check'
            _logger.info(">>>>>moh>>>> Starting Duplicate Check...")

            if mobile_invoice_number:
                # 1. البحث عن السجل الموجود
                date_threshold = datetime.utcnow() - timedelta(days=7)
                existing_so = env['sale.order'].sudo().search([
                    ('client_order_ref', '=', mobile_invoice_number),
                    ('user_id', '=', current_user.id),
                    ('create_date', '>=', date_threshold),
                    ('state', '!=', 'cancel')
                ], limit=1)

                if not existing_so:
                    existing_inv = env['account.move'].sudo().search([
                        ('mobile_invoice_number', '=', mobile_invoice_number),
                        ('invoice_user_id', '=', current_user.id),
                        ('create_date', '>=', date_threshold),
                        ('move_type', '=', 'out_invoice'),
                        ('state', '!=', 'cancel')
                    ], limit=1)
                    if existing_inv:
                        existing_so = env['sale.order'].sudo().search([
                            ('invoice_ids', 'in', [existing_inv.id])
                        ], limit=1)

                if existing_so:
                    _logger.info(f">>>>>moh>>>> Duplicate Reference Found: {mobile_invoice_number}")

                    # تحضير بيانات الرد (نحتاجها سواء للنجاح أو للخطأ)
                    final_inv = existing_so.invoice_ids.filtered(lambda x: x.state != 'cancel')[:1]
                    resp = {
                        "sale_order": {
                            "id": existing_so.id,
                            "name": noneify(existing_so.name),
                            "state": noneify(existing_so.state)
                        },
                        "invoice": {
                            "id": final_inv.id if final_inv else None,
                            "name": noneify(final_inv.name) if final_inv else None,
                            "state": noneify(final_inv.state) if final_inv else None,
                            "payment_state": noneify(final_inv.payment_state) if final_inv else None,
                            "mobile_invoice_number": noneify(mobile_invoice_number),
                            "amount_total": final_inv.amount_total if final_inv else existing_so.amount_total,
                            "amount_residual": final_inv.amount_residual if final_inv else 0.0,
                        },
                        "payments_details": payment_list,
                        "is_duplicate": True
                    }

                    # ========================================================
                    # اللحظة الحاسمة: هل هو تكرار صحيح (Retry) أم خطأ (Conflict)؟
                    # ========================================================

                    # الحالة 1: العميل مختلف -> خطأ وتضارب (409)
                    if int(partner_id) != existing_so.partner_id.id:
                        msg = f"هناك تكرار بأرقام الفواتير لعميل مختلف! (الموجود: {existing_so.partner_id.name})"
                        _logger.warning(f">>>>>moh>>>> Conflict: {msg}")

                        # إرجاع خطأ لأن العميل مختلف
                        return format_response(False, msg, resp, error_code=-409, http_status=409)

                    # الحالة 2: نفس العميل -> نجاح وتأكيد (200)
                    else:
                        _logger.info(">>>>>moh>>>> Valid Retry (Same Customer). Returning 200 OK.")
                        return format_response(True, "تم حفظ الفاتورة بنجاح (مكررة).", resp, http_status=200)

            _logger.info(">>>>>moh>>>> No duplicate found. Proceeding...")
            # ===============================================================================
            requested_status_raw = (body.get('order_status') or body.get('status') or body.get('state') or '').strip()
            requested_status = requested_status_raw.lower() if requested_status_raw else ''

            # معالجة الصورة
            image = body.get('image')
            attachment_name = f"attachment_{datetime.utcnow().strftime('%Y%m%d%H%M%S')}"
            attachment_datas = None
            SKIP_IMAGE_VALUES = {'no need', 'no_need', 'noneed', 'none', 'null', 'skip', 'false', 'n/a', 'na', ''}

            def is_skip_value(val):
                if not val: return True
                if isinstance(val, str): return val.strip().lower() in SKIP_IMAGE_VALUES
                return False

            if isinstance(image, dict):
                if image.get('name') and not is_skip_value(image.get('name')): attachment_name = image['name']
                raw_data = image.get('data') or image.get('base64') or image.get('content')
                if not is_skip_value(raw_data): attachment_datas = raw_data
            elif isinstance(image, str):
                if not is_skip_value(image): attachment_datas = image

            _logger.info(f">>>>>moh>>>> Image processing done. Has attachment: {bool(attachment_datas)}")

            msl_results = body.get('msl_results') or []

            error_stage = 'validation'
            if not partner_id:
                _logger.error(">>>>>moh>>>> Validation Failed: partner_id missing")
                return format_response(False, "partner_id is required", error_code=-101, http_status=400)
            if not items or not isinstance(items, list):
                _logger.error(">>>>>moh>>>> Validation Failed: items missing or invalid")
                return format_response(False, "items must be a non-empty list", error_code=-102, http_status=400)
            if requested_status != 'invoice':
                _logger.info(f">>>>>moh>>>> Status is '{requested_status}', not 'invoice'. Returning early.")
                return format_response(True, "Status is not invoice", {}, http_status=200)

            # ========================================================================================
            #  بداية المعاملة (TRANSACTION START)
            # ========================================================================================
            _logger.info(">>>>>moh>>>> Starting SQL Savepoint Transaction...")
            # تمت إعادة Savepoint للوضع الطبيعي
            with env.cr.savepoint():

                # 1. التحقق من البروفايل والمستودع
                error_stage = 'sale_order'
                _logger.info(">>>>>moh>>>> Step 1: Checking Sales Rep Profile and Warehouse")
                RepProfile = env['sales.rep.profile'].sudo()
                rep_profile = RepProfile.search([('user_id', '=', current_user.id)], limit=1)

                if not rep_profile or not rep_profile.location_id:
                    _logger.error(">>>>>moh>>>> No profile or location found for user")
                    raise UserError("No location assigned to this sales representative")

                if rep_profile.attachment_mandatory and not attachment_datas:
                    _logger.error(">>>>>moh>>>> Attachment is mandatory but missing")
                    # raise UserError("Attachment is mandatory for this sales representative.")

                # هذا هو الموقع الصحيح الذي يجب الإخراج منه حصراً
                rep_loc = rep_profile.location_id

                Warehouse = env['stock.warehouse'].sudo()
                wh = Warehouse.search([('lot_stock_id', 'parent_of', rep_loc.id)], limit=1)
                if not wh: wh = Warehouse.search([('view_location_id', 'parent_of', rep_loc.id)], limit=1)
                if not wh:
                    main_wh = Warehouse.search([('company_id', '=', current_user.company_id.id)], limit=1)
                    if main_wh:
                        wh = main_wh
                    else:
                        raise UserError("No warehouse found for the sales rep location or company")

                _logger.info(f">>>>>moh>>>> Warehouse selected: {wh.name} (ID: {wh.id}), Loc: {rep_loc.name}")

                SaleOrder = env['sale.order'].sudo()
                Attachment = env['ir.attachment'].sudo()
                SOL = env['sale.order.line'].sudo()

                # 2. إنشاء أمر البيع
                _logger.info(">>>>>moh>>>> Step 2: Creating Sale Order record")
                so_vals = {
                    'partner_id': int(partner_id),
                    'user_id': current_user.id,
                    'warehouse_id': wh.id,
                }
                if mobile_invoice_number:
                    so_vals['client_order_ref'] = mobile_invoice_number

                so = SaleOrder.create(so_vals)
                _logger.info(f">>>>>moh>>>> SO Created with ID: {so.id}")

                # 3. إرفاق الصورة
                if attachment_datas:
                    _logger.info(">>>>>moh>>>> Step 3: Creating Attachment")
                    Attachment.create({
                        'name': attachment_name, 'type': 'binary', 'datas': attachment_datas,
                        'res_model': 'sale.order', 'res_id': so.id, 'mimetype': 'image/jpeg',
                    })

                # 4. إضافة البنود والهدايا
                _logger.info(">>>>>moh>>>> Step 4: Adding Order Lines")
                for it in items:
                    product_id = it.get('product_id')
                    qty = it.get('quantity') or it.get('qty') or 1.0
                    price = it.get('price_unit') or it.get('price')
                    is_reward = it.get('reward')

                    if not product_id:
                        raise UserError("Each line requires product_id")

                    vals = {
                        'order_id': so.id,
                        'product_id': int(product_id),
                        'product_uom_qty': float(qty),
                    }
                    if price is not None:
                        vals['price_unit'] = float(price)

                    if is_reward is True:
                        vals['discount'] = 100.0
                        prod_obj = env['product.product'].sudo().browse(int(product_id))
                        prod_name = prod_obj.display_name or prod_obj.name
                        linked_products = []
                        programs = env['loyalty.program'].sudo().search([('active', '=', True)])
                        for prog in programs:
                            for reward in prog.reward_ids:
                                if reward.reward_type == 'product' and prod_obj in reward.reward_product_ids:
                                    for rule in prog.rule_ids:
                                        for orig_product in rule.product_ids:
                                            prod_name_str = orig_product.display_name or orig_product.name
                                            if orig_product not in linked_products:
                                                linked_products.append(prod_name_str)
                        if linked_products:
                            vals['name'] = f"{prod_name} (هدية مجانية)"
                        else:
                            vals['name'] = f"{prod_name} (هدية مجانية)"

                    SOL.create(vals)
                _logger.info(">>>>>moh>>>> Order Lines Created.")

                # 5. حفظ MSL
                _logger.info(">>>>>moh>>>> Step 5: Saving MSL results")
                msl_saved, msl_via = self._save_msl_results(env, so, msl_results)

                # 6. تأكيد الأمر
                _logger.info(">>>>>moh>>>> Step 6: Confirming Sale Order")
                if so.state in ('draft', 'sent'):
                    so.action_confirm()

                # 7. معالجة التسليم (Delivery)
                error_stage = 'picking'
                _logger.info(">>>>>moh>>>> Step 7: Processing Delivery Pickings")
                for p in so.picking_ids.sudo():
                    _logger.info(f">>>>>moh>>>> Processing Picking ID: {p.id}, State: {p.state}")
                    if p.state in ('done', 'cancel'): continue
                    if getattr(p, 'batch_id', False): p.write({'batch_id': False})

                    # محاولة تطبيق النوع عبر الدالة المساعدة
                    self._apply_rep_outgoing_type(env, p, rep_profile, rep_loc, wh)

                    # ==== (Fix) إجبار الموقع بالقوة لضمان الخصم من مستودع المندوب ====
                    p.write({'location_id': rep_loc.id})

                    # تحديث الحركات الداخلية أيضاً (Moves)
                    for move in p.move_ids_without_package:
                        move.write({'location_id': rep_loc.id})
                        # تحديث الخطوط التفصيلية (Move Lines) إن وجدت
                        for line in move.move_line_ids:
                            line.write({'location_id': rep_loc.id})
                    # ================================================================

                    if p.state == 'draft':
                        _logger.info(">>>>>moh>>>> Confirming draft picking")
                        p.action_confirm()

                    try:
                        _logger.info(">>>>>moh>>>> Validating Picking...")
                        self._validate_picking(env, p)
                        _logger.info(">>>>>moh>>>> Picking Validated Successfully")
                    except Exception as e:
                        _logger.error(f">>>>>moh>>>> Delivery Validation Failed: {str(e)}")
                        raise UserError(f"Delivery Validation Failed: {str(e)}")

                # 8. إنشاء الفاتورة
                error_stage = 'invoice'
                _logger.info(">>>>>moh>>>> Step 8: Creating Invoice")
                try:
                    so._compute_invoice_status()
                except:
                    pass

                invoices = so._create_invoices(final=False)
                if not invoices and 'sale.advance_payment.inv' in env:
                    _logger.info(">>>>>moh>>>> Using Advance Payment Wizard fallback")
                    wiz = env['sale.advance_payment.inv'].sudo().create({'advance_payment_method': 'delivered'})
                    wiz = wiz.with_context(active_model='sale.order', active_ids=[so.id], open_invoices=False)
                    pre = so.invoice_ids.ids
                    wiz.create_invoices()
                    so.flush()
                    new_ids = [i for i in so.invoice_ids.ids if i not in pre]
                    invoices = env['account.move'].browse(new_ids)

                if not invoices:
                    _logger.error(">>>>>moh>>>> Failed to create invoice")
                    raise UserError("Cannot create an invoice. Please check delivery status or invoicing policy.")

                _logger.info(f">>>>>moh>>>> Invoices Created: {invoices.ids}")

                # 9. Cash Rounding
                CashRounding = env['account.cash.rounding'].sudo()
                cash_rounding = CashRounding.search([('name', '=', 'NAD Cash Rounding')], limit=1)
                if cash_rounding:
                    _logger.info(">>>>>moh>>>> Step 9: Applying Cash Rounding")
                    invoices.write({'invoice_cash_rounding_id': cash_rounding.id})

                # 10. ترحيل الفاتورة
                _logger.info(">>>>>moh>>>> Step 10: Posting Invoice")
                to_post = invoices.filtered(lambda m: m.state == 'draft')
                if to_post:
                    to_post.action_post()

                if mobile_invoice_number:
                    invoices.sudo().write({'mobile_invoice_number': mobile_invoice_number})

                inv = invoices[:1]
                _logger.info(f">>>>>moh>>>> Primary Invoice ID: {inv.id}, State: {inv.state}")

                # 11. تسجيل الدفعات (Payments)
                error_stage = 'payment'
                _logger.info(">>>>>moh>>>> Step 11: Registering Payments")
                payments_info = []

                # ==== (إضافة: تعريف المتغير هنا لتجنب الخطأ) ====
                pay_date = None
                # ================================================

                if not isinstance(payment_list, list):
                    payment_list = [payment_list]

                for pay in payment_list:
                    if inv.state == 'posted' and inv.payment_state in ('paid', 'in_payment'):
                        break
                    if inv.amount_residual == 0:
                        break

                    if not isinstance(pay, dict): continue

                    pay_amount = pay.get('amount')
                    amount_to_pay = float(pay_amount) if pay_amount is not None else inv.amount_residual

                    if amount_to_pay <= 0:
                        continue

                    # تحديث المتغير pay_date إذا وجد تاريخ
                    pay_date = pay.get('payment_date') or pay.get('date')
                    pay_currency_val = pay.get('currency')
                    pay_currency_id = pay.get('currency_id')
                    pay_currency_code = pay.get('currency_code') or pay.get('currency')

                    fallback_cur = inv.currency_id or (current_user.company_id and current_user.company_id.currency_id)
                    pay_currency = self._resolve_currency(
                        env, pay_currency_val, cur_id=pay_currency_id, cur_code=pay_currency_code, fallback=fallback_cur
                    )
                    if not pay_currency: continue

                    journal = self._get_rep_journal_for_currency(env, rep_profile, pay_currency)
                    if not journal: continue

                    ctx = {'active_model': 'account.move', 'active_ids': [inv.id]}
                    Register = env['account.payment.register'].with_context(ctx).sudo()
                    reg_vals = {
                        'journal_id': journal.id,
                        'amount': amount_to_pay,
                    }
                    if pay_date:
                        reg_vals['payment_date'] = pay_date

                    try:
                        _logger.info(
                            f">>>>>moh>>>> Creating Payment Register. Amount: {amount_to_pay}, Journal: {journal.name}")
                        reg = Register.create(reg_vals)
                        reg.action_create_payments()

                        payments_info.append({
                            "amount": reg_vals['amount'],
                            "currency": pay_currency.name,
                            "journal_id": journal.id,
                            "journal_name": journal.name,
                            "payment_date": reg_vals.get('payment_date') or str(fields.Date.today())
                        })

                    except UserError as e:
                        if "nothing left to pay" in str(e).lower():
                            _logger.warning(
                                f"Payment logic: Skipped registration for {mobile_invoice_number} - {str(e)}")
                            continue
                        else:
                            raise e

                    except Exception as e:
                        _logger.error(f">>>>>moh>>>> Payment Error: {str(e)}")
                        raise UserError(f"Payment Failed: {str(e)}")

                resp = {
                    "sale_order": {
                        "id": so.id,
                        "name": noneify(so.name),
                        "state": noneify(so.state),
                    },
                    "invoice": {
                        "id": inv.id,
                        "name": noneify(inv.name),
                        "state": noneify(inv.state),
                        "payment_state": noneify(inv.payment_state),
                        "mobile_invoice_number": noneify(getattr(inv, 'mobile_invoice_number', None)),
                        "amount_total": inv.amount_total,
                        "amount_residual": inv.amount_residual,
                    },
                    "payments_details": payments_info,
                    # تم التعديل هنا ليعمل الكود بدون خطأ (حذفنا الشرط if locals لأنه صار ماله داعي)
                    "payment_date": noneify(pay_date),
                    "msl_results_saved": int(msl_saved),
                    "msl_saved_via": noneify(msl_via),
                    "cash_rounding_applied": cash_rounding.name if cash_rounding else None,
                }

                _logger.info(">>>>>moh>>>> All steps completed successfully. Returning response.")

                # تمت إزالة "الفخ" (Commit + Error) ليصبح الكود جاهزاً

                return format_response(True, "CashVan invoice created, delivered and paid.", resp, http_status=200)

            # ==================== نهاية الـ SAVEPOINT ====================

        except (UserError, ValidationError) as e:
            _logger.error(f">>>>>moh>>>> Known Error Caught (Stage: {error_stage}): {str(e)}")
            self._log_cashvan_failure(
                env=env,
                user_id=current_user.id,
                partner_id=partner_id,
                mobile_invoice_number=mobile_invoice_number,
                error_message=str(e),
                error_stage=error_stage,
                payload_text=payload_text,
            )
            return format_response(False, str(e), error_code=-400, http_status=400)

        except Exception as e:
            _logger.error(f">>>>>moh>>>> CRITICAL Unknown Error Caught (Stage: {error_stage}): {str(e)}")
            self._log_cashvan_failure(
                env=env,
                user_id=current_user.id,
                partner_id=partner_id,
                mobile_invoice_number=mobile_invoice_number,
                error_message=f"Internal Error: {str(e)}",
                error_stage=error_stage,
                payload_text=payload_text,
            )
            return format_response(False, f"Internal error: {str(e)}", error_code=-500, http_status=500)

    # CashVan: Return (Receipt -> Credit Note -> Pay)
    # -----------------------------
    @http.route(
        ['/sales_rep_manager/<string:api_version>/cashvan/return'],
        type='http', auth='none', methods=['POST', 'OPTIONS'], csrf=False, cors='*'
    )
    @jwt_required()
    def cashvan_return(self, **kwargs):
        # 1. CORS Preflight
        if request.httprequest.method == 'OPTIONS':
            return json_response({"ok": True}, status=200)

        env = kwargs["_jwt_env"]
        current_user = env['res.users'].browse(kwargs["_jwt_user_id"])

        # استيراد المكتبات
        from odoo.exceptions import UserError, ValidationError
        import json, base64
        from datetime import datetime, timedelta
        import logging

        # تعريف اللوجر
        _logger = logging.getLogger(__name__)
        _logger.info(f">>>>>moh>>>> START: cashvan_return called by User ID: {current_user.id}")

        # ================= LOGGING ONLY =================
        error_stage = 'other'
        payload_text = None
        partner_id = None
        mobile_invoice_number = None
        # =================================================

        try:
            _logger.info(">>>>>moh>>>> Reading request body (Return)...")
            body, error = self._get_body()
            if error:
                error_stage = 'validation'
                _logger.error(f">>>>>moh>>>> Body parsing error: {error}")
                return format_response(False, error, error_code=-100, http_status=400)

            try:
                payload_text = json.dumps(body, ensure_ascii=False)
            except Exception:
                payload_text = str(body)

            partner_id = body.get('partner_id')
            items = body.get('items') or body.get('lines') or []
            mobile_invoice_number = body.get('mobile_invoice_number')
            base_note = (body.get('note') or '').strip()
            incoming_msl_results = body.get('msl_results') or []

            # ++++ (تعديل 1) سحبنا تعريف قائمة الدفعات للأعلى لنستخدمها في الرد ++++
            payment_list = body.get('payment') or []

            _logger.info(
                f">>>>>moh>>>> Payload Parsed (Return). Partner: {partner_id}, Mobile Ref: {mobile_invoice_number}, Items: {len(items)}")

            # ==================== (1) التحقق من التكرار (Idempotency Check - Return) ====================
            error_stage = 'duplicate_check'
            _logger.info(">>>>>moh>>>> Starting Duplicate Check (Return)...")
            if mobile_invoice_number:
                # التحقق خلال آخر 7 أيام
                date_threshold = datetime.utcnow() - timedelta(days=7)

                # البحث عن إشعار دائن (Credit Note) موجود مسبقاً
                existing_credit = env['account.move'].sudo().search([
                    ('mobile_invoice_number', '=', mobile_invoice_number),
                    ('invoice_user_id', '=', current_user.id),
                    ('move_type', '=', 'out_refund'),  # مرتجع
                    ('create_date', '>=', date_threshold),
                    ('state', '!=', 'cancel')
                ], limit=1)

                if existing_credit:
                    _logger.info(f">>>>>moh>>>> Duplicate Return found! Existing Credit Note ID: {existing_credit.id}")

                    # محاولة العثور على الحركة المخزنية المرتبطة (اختياري للعرض)
                    existing_picking = env['stock.picking'].sudo().search([
                        ('origin', '=', mobile_invoice_number),
                        ('location_dest_id.usage', '=', 'internal')
                    ], limit=1)

                    # تحضير هيكل الرد
                    resp = {
                        "receipt": {
                            "id": existing_picking.id if existing_picking else None,
                            "name": noneify(existing_picking.name) if existing_picking else None,
                            "state": noneify(existing_picking.state) if existing_picking else None,
                            "dest_location": noneify(
                                getattr(existing_picking.location_dest_id, 'complete_name', None)
                                or getattr(existing_picking.location_dest_id, 'display_name', None)
                            ) if existing_picking else None,
                            "note": noneify(getattr(existing_picking, 'note', None)) if existing_picking else None,
                        },
                        "credit_note": {
                            "id": existing_credit.id,
                            "name": noneify(existing_credit.name),
                            "state": noneify(existing_credit.state),
                            "payment_state": noneify(existing_credit.payment_state),
                            "mobile_invoice_number": noneify(existing_credit.mobile_invoice_number),
                            "amount_total": existing_credit.amount_total,
                            "amount_residual": existing_credit.amount_residual,
                            "ref": noneify(existing_credit.ref),
                        },
                        "payments_details": payment_list,  # استخدام القائمة القادمة من الطلب
                        "payment_date": noneify(existing_credit.invoice_date or existing_credit.date),
                        "note": "Duplicate return detected.",
                        "is_duplicate": True
                    }

                    # ========================================================
                    # اللحظة الحاسمة: هل هو تكرار صحيح (Retry) أم خطأ (Conflict)؟
                    # ========================================================

                    # الحالة 1: العميل مختلف -> خطأ وتضارب (409)
                    if int(partner_id) != existing_credit.partner_id.id:
                        msg = f"هناك تكرار بأرقام المرتجعات لعميل مختلف! (الموجود: {existing_credit.partner_id.name})"
                        _logger.warning(f">>>>>moh>>>> Conflict: {msg}")

                        # تسجيل الخطأ في اللوج فقط عند وجود تضارب حقيقي
                        self._log_cashvan_failure(
                            env=env,
                            user_id=current_user.id,
                            partner_id=partner_id,
                            mobile_invoice_number=mobile_invoice_number,
                            error_message=msg,
                            error_stage='duplicate_check',
                            payload_text=payload_text
                        )
                        return format_response(False, msg, resp, error_code=-409, http_status=409)

                    # الحالة 2: نفس العميل -> نجاح وتأكيد (200)
                    else:
                        _logger.info(">>>>>moh>>>> Valid Retry (Same Customer - Return). Returning 200 OK.")
                        return format_response(True, "تم حفظ المرتجع بنجاح (مكرر).", resp, http_status=200)

            _logger.info(">>>>>moh>>>> No duplicate return found. Proceeding...")
            # ===========================================================================

            # payment_list تم تعريفها في الأعلى

            error_stage = 'validation'
            if not partner_id:
                _logger.error(">>>>>moh>>>> Validation Failed: partner_id missing")
                return format_response(False, "partner_id is required", error_code=-101, http_status=400)
            if not items or not isinstance(items, list):
                _logger.error(">>>>>moh>>>> Validation Failed: items missing")
                return format_response(False, "items must be a non-empty list", error_code=-102, http_status=400)

            # ========================================================================================
            #  بداية المعاملة (TRANSACTION BLOCK)
            # ========================================================================================
            _logger.info(">>>>>moh>>>> Starting SQL Savepoint Transaction (Return)...")
            with env.cr.savepoint():

                RepProfile = env['sales.rep.profile'].sudo()
                Picking = env['stock.picking'].sudo()
                Move = env['stock.move'].sudo()
                Product = env['product.product'].sudo()
                AccountMove = env['account.move'].sudo()

                error_stage = 'picking_preparation'
                _logger.info(">>>>>moh>>>> Checking Rep Profile")
                rep_profile = RepProfile.search([('user_id', '=', current_user.id)], limit=1)
                if not rep_profile or not rep_profile.location_id:
                    raise UserError("No location assigned to this sales representative")

                rep_loc = rep_profile.location_id

                ptype = self._find_return_receipt_type(env, getattr(current_user, 'company_id', False))
                if not ptype:
                    raise UserError("No suitable incoming 'Return' operation type found.")

                # 1. إنشاء Picking
                error_stage = 'picking'
                _logger.info(">>>>>moh>>>> Creating Return Picking")
                picking = Picking.create({
                    'picking_type_id': ptype.id,
                    'partner_id': int(partner_id),
                    'location_dest_id': rep_loc.id,
                    'origin': mobile_invoice_number or "Mobile Return",
                })

                dmg_loc = self._get_damaged_location(env, rep_loc, getattr(current_user, 'company_id', False))
                damaged_notes = []

                # 2. معالجة حركات المخزون
                _logger.info(">>>>>moh>>>> Creating Stock Moves")
                for it in items:
                    product_id = it.get('product_id')
                    qty = it.get('quantity') or it.get('qty') or 1.0
                    if not product_id:
                        raise UserError("Each line requires product_id")

                    is_damaged = bool(it.get('damaged') is True)

                    Move.create({
                        'name': 'Mobile Return',
                        'picking_id': picking.id,
                        'product_id': int(product_id),
                        'product_uom_qty': float(qty),
                        'location_id': ptype.default_location_src_id.id,
                        'location_dest_id': (dmg_loc.id if is_damaged else rep_loc.id),
                    })

                    if is_damaged:
                        try:
                            _prod = Product.browse(int(product_id))
                            code = noneify(_prod.default_code) or ""
                            pname = _prod.name or f'Product {product_id}'

                            damaged_notes.append(
                                f"- [{code}] {pname}: {float(qty)}" if code else f"- {pname}: {float(qty)}"
                            )
                        except Exception:
                            damaged_notes.append(f"- Product {product_id}: {float(qty)}")

                if picking.state == 'draft':
                    picking.action_confirm()

                # 3. التأكيد (Validation)
                error_stage = 'picking_validation'
                _logger.info(">>>>>moh>>>> Validating Return Picking")
                try:
                    self._fill_done_quantities(picking)
                    res = picking.with_user(SUPERUSER_ID).button_validate()
                    self._process_wizard(env, res, 'stock.immediate.transfer', [picking.id])
                    if picking.state not in ('done', 'cancel'):
                        res2 = picking.with_user(SUPERUSER_ID).button_validate()
                        self._process_wizard(env, res2, 'stock.backorder.confirmation', [picking.id])
                    self._process_wizard(env, res, 'stock.backorder.confirmation', [picking.id])
                except Exception as e:
                    raise UserError(f"Picking Validation Failed: {str(e)}")

                # 4. معالجة الفاتورة المرتجعة (Credit Note)
                error_stage = 'credit_note_create'
                _logger.info(">>>>>moh>>>> Creating Credit Note")
                lines_vals = []
                for it in items:
                    product_id = int(it.get('product_id'))
                    product = Product.browse(product_id)
                    qty = float(it.get('quantity') or it.get('qty') or 1.0)
                    price_unit = it.get('price_unit') or product.lst_price
                    is_reward = it.get('reward')
                    discount = float(it.get('discount') or 0.0)

                    # حماية: الخصم بين 0 و 100
                    if discount < 0:
                        discount = 0.0
                    elif discount > 100:
                        discount = 100.0

                    line_val = {
                        'product_id': product.id,
                        'quantity': qty,
                        'price_unit': float(price_unit),
                        'discount': discount,
                    }

                    if is_reward is True:
                        line_val['discount'] = 100.0
                        prod_name = product.sudo().display_name or product.sudo().name
                        line_val['name'] = f"{prod_name} (إرجاع هدية مجانية)"

                    lines_vals.append((0, 0, line_val))

                final_note = base_note
                if damaged_notes:
                    dmg_text = "Damaged items:\n" + "\n".join(damaged_notes)
                    final_note = f"{base_note}\n{dmg_text}".strip() if base_note else dmg_text

                credit_vals = {
                    'move_type': 'out_refund',
                    'partner_id': int(partner_id),
                    'invoice_line_ids': lines_vals,
                }
                if final_note:
                    credit_vals['ref'] = final_note
                    credit_vals['narration'] = final_note

                credit = AccountMove.create(credit_vals)

                # 5. Cash Rounding
                CashRounding = env['account.cash.rounding'].sudo()
                cash_rounding = CashRounding.search([('name', '=', 'NAD Cash Rounding')], limit=1)

                if cash_rounding:
                    _logger.info(">>>>>moh>>>> Applying Cash Rounding")
                    credit.write({'invoice_cash_rounding_id': cash_rounding.id})
                else:
                    _logger.warning(">>>>>moh>>>> CashVan: Cash rounding 'NAD Cash Rounding' not found")

                if mobile_invoice_number:
                    credit.write({'mobile_invoice_number': mobile_invoice_number})

                if credit.state == 'draft':
                    _logger.info(">>>>>moh>>>> Posting Credit Note")
                    credit.action_post()

                if incoming_msl_results and isinstance(incoming_msl_results, list):
                    try:
                        env['ir.attachment'].sudo().create({
                            'name': f"msl_results_return_{credit.name or credit.id}.json",
                            'type': 'binary',
                            'datas': base64.b64encode(
                                json.dumps(incoming_msl_results, ensure_ascii=False).encode('utf-8')
                            ).decode('utf-8'),
                            'res_model': 'account.move',
                            'res_id': credit.id,
                            'mimetype': 'application/json',
                        })
                    except Exception:
                        pass

                # 6. الدفع (Payment)
                error_stage = 'payment'
                _logger.info(">>>>>moh>>>> Registering Payments (Return)")
                payments_info = []

                if not isinstance(payment_list, list):
                    payment_list = [payment_list]

                for pay in payment_list:
                    if credit.state == 'posted' and credit.payment_state in ('paid', 'in_payment'):
                        break
                    if credit.amount_residual == 0:
                        break

                    if not isinstance(pay, dict): continue

                    pay_amount = pay.get('amount')
                    amount_to_pay = float(pay_amount) if pay_amount is not None else credit.amount_residual

                    if amount_to_pay <= 0:
                        continue

                    pay_date = pay.get('payment_date') or pay.get('date')
                    pay_currency_val = pay.get('currency')
                    pay_currency_id = pay.get('currency_id')
                    pay_currency_code = pay.get('currency_code') or pay.get('currency')

                    credit_date = getattr(credit, 'invoice_date', None) or getattr(credit, 'date', None)
                    if not pay_date and credit_date:
                        pay_date = credit_date

                    fallback_cur = credit.currency_id or (
                            current_user.company_id and current_user.company_id.currency_id)
                    pay_currency = self._resolve_currency(
                        env, pay_currency_val, cur_id=pay_currency_id, cur_code=pay_currency_code, fallback=fallback_cur
                    )
                    if not pay_currency:
                        continue

                    journal = self._get_rep_journal_for_currency(env, rep_profile, pay_currency)
                    if not journal:
                        raise UserError(f"No cash journal mapped for currency {pay_currency.name}.")

                    ctx = {'active_model': 'account.move', 'active_ids': [credit.id]}
                    Register = env['account.payment.register'].with_context(ctx).sudo()

                    reg_vals = {
                        'journal_id': journal.id,
                        'amount': amount_to_pay
                    }
                    if pay_date:
                        reg_vals['payment_date'] = pay_date

                    try:
                        _logger.info(f">>>>moh>>>> Creating Payment. Amount: {amount_to_pay}, Journal: {journal.name}")
                        reg = Register.create(reg_vals)
                        reg.action_create_payments()

                        payments_info.append({
                            "amount": reg_vals['amount'],
                            "currency": pay_currency.name,
                            "journal_id": journal.id,
                            "journal_name": journal.name,
                            "payment_date": str(reg_vals.get('payment_date') or fields.Date.today())
                        })
                    except UserError as e:
                        if "nothing left to pay" in str(e).lower():
                            _logger.warning(
                                f"Payment logic: Skipped registration for {mobile_invoice_number} - {str(e)}")
                            continue
                        else:
                            raise e

                    except Exception as e:
                        _logger.error(f">>>>>moh>>>> Payment Error: {str(e)}")
                        raise UserError(f"Payment Failed for {pay_currency.name}: {str(e)}")

                if final_note:
                    try:
                        picking.write({'note': final_note})
                    except:
                        pass

                # 7. الرد النهائي (نجاح)
                resp = {
                    "receipt": {
                        "id": picking.id,
                        "name": noneify(picking.name),
                        "state": noneify(picking.state),
                        "dest_location": noneify(
                            getattr(picking.location_dest_id, 'complete_name', None)
                            or getattr(picking.location_dest_id, 'display_name', None)
                        ),
                        "note": noneify(getattr(picking, 'note', None)),
                    },
                    "credit_note": {
                        "id": credit.id,
                        "name": noneify(credit.name),
                        "state": noneify(credit.state),
                        "payment_state": noneify(credit.payment_state),
                        "mobile_invoice_number": noneify(getattr(credit, 'mobile_invoice_number', None)),
                        "amount_total": credit.amount_total,
                        "amount_residual": credit.amount_residual,
                        "ref": noneify(getattr(credit, 'ref', None)),
                    },
                    "payments_details": payments_info,
                    "payment_date": noneify(pay_date),
                }

                _logger.info(">>>>>moh>>>> Return Transaction Completed Successfully.")
                return format_response(True, "CashVan return created and paid.", resp, http_status=200)

            # ==================== نهاية الـ SAVEPOINT ====================

        except (UserError, ValidationError) as e:
            _logger.error(f">>>>>moh>>>> Known Error (Return): {str(e)}")
            self._log_cashvan_failure(
                env=env,
                user_id=current_user.id,
                partner_id=partner_id,
                mobile_invoice_number=mobile_invoice_number,
                error_message=str(e),
                error_stage=error_stage,
                payload_text=payload_text,
            )
            return format_response(False, str(e), error_code=-400, http_status=400)

        except Exception as e:
            _logger.error(f">>>>>moh>>>> CRITICAL Error (Return): {str(e)}")
            self._log_cashvan_failure(
                env=env,
                user_id=current_user.id,
                partner_id=partner_id,
                mobile_invoice_number=mobile_invoice_number,
                error_message=f"Internal Error: {str(e)}",
                error_stage=error_stage,
                payload_text=payload_text,
            )
            return format_response(False, f"Internal error: {str(e)}", error_code=-500, http_status=500)

    @http.route(
        ['/sales_rep_manager/<string:api_version>/cashvan/so/create'],
        type='http', auth='none', methods=['POST', 'OPTIONS'], csrf=False, cors='*'
    )
    @jwt_required()
    def cashvan_so_create(self, **kwargs):
        if request.httprequest.method == 'OPTIONS':
            return json_response({"ok": True}, status=200)

        env = kwargs["_jwt_env"]
        current_user = env['res.users'].browse(kwargs["_jwt_user_id"])

        try:
            from datetime import datetime

            body, error = self._get_body()
            if error:
                return format_response(False, error, error_code=-100, http_status=400)

            partner_id = body.get('partner_id')
            items = body.get('items') or body.get('lines') or []
            mobile_invoice_number = body.get('mobile_invoice_number')

            # ==================== معالجة الصورة ====================
            image = body.get('image')
            attachment_name = f"attachment_{datetime.utcnow().strftime('%Y%m%d%H%M%S')}"
            attachment_datas = None

            SKIP_IMAGE_VALUES = {
                'no need', 'no_need', 'noneed',
                'none', 'null', 'skip',
                'false', 'n/a', 'na', ''
            }

            def is_skip_value(val):
                if not val:
                    return True
                if isinstance(val, str):
                    return val.strip().lower() in SKIP_IMAGE_VALUES
                return False

            if isinstance(image, dict):
                if image.get('name') and not is_skip_value(image.get('name')):
                    attachment_name = image['name']
                raw_data = image.get('data') or image.get('base64') or image.get('content')
                if not is_skip_value(raw_data):
                    attachment_datas = raw_data
            elif isinstance(image, str):
                if not is_skip_value(image):
                    attachment_datas = image
            # ==========================================================

            msl_results = body.get('msl_results') or []

            if not partner_id:
                return format_response(False, "partner_id is required", error_code=-101, http_status=400)
            if not items or not isinstance(items, list):
                return format_response(False, "items must be a non-empty list", error_code=-102, http_status=400)

            # --- إلغاء فصل القوائم ---

            RepProfile = env['sales.rep.profile'].sudo()
            rep_profile = RepProfile.search([('user_id', '=', current_user.id)], limit=1)
            if not rep_profile or not rep_profile.location_id:
                return format_response(
                    False,
                    "No location assigned to this sales representative",
                    error_code=-404,
                    http_status=400
                )

            if rep_profile.attachment_mandatory and not attachment_datas:
                return format_response(
                    False,
                    "Attachment is mandatory for this sales representative.",
                    error_code=-150,
                    http_status=400
                )

            rep_loc = rep_profile.location_id

            Warehouse = env['stock.warehouse'].sudo()
            wh = Warehouse.search([('lot_stock_id', 'parent_of', rep_loc.id)], limit=1)
            if not wh:
                wh = Warehouse.search([('view_location_id', 'parent_of', rep_loc.id)], limit=1)
            if not wh:
                main_wh = Warehouse.search([('company_id', '=', current_user.company_id.id)], limit=1)
                if main_wh:
                    wh = main_wh
                else:
                    return format_response(
                        False,
                        "No warehouse found for the sales rep location or company",
                        error_code=-405,
                        http_status=400
                    )

            SaleOrder = env['sale.order'].sudo()
            Attachment = env['ir.attachment'].sudo()
            SOL = env['sale.order.line'].sudo()

            so = SaleOrder.create({
                'partner_id': int(partner_id),
                'user_id': current_user.id,
                'warehouse_id': wh.id,
            })

            if attachment_datas:
                Attachment.create({
                    'name': attachment_name,
                    'type': 'binary',
                    'datas': attachment_datas,
                    'res_model': 'sale.order',
                    'res_id': so.id,
                    'mimetype': 'image/jpeg',
                })

            # ==================== معالجة المنتجات والهدايا ====================
            for it in items:
                product_id = it.get('product_id')
                qty = it.get('quantity') or it.get('qty') or 1.0
                price = it.get('price_unit') or it.get('price')
                is_reward = it.get('reward')

                if not product_id:
                    return format_response(False, "Each line requires product_id", error_code=-103, http_status=400)

                vals = {
                    'order_id': so.id,
                    'product_id': int(product_id),
                    'product_uom_qty': float(qty),
                }
                if price is not None:
                    vals['price_unit'] = float(price)

                # ------------------- منطق الهدية -------------------
                if is_reward is True:
                    vals['discount'] = 100.0
                    prod_obj = env['product.product'].sudo().browse(int(product_id))
                    prod_name = prod_obj.display_name or prod_obj.name

                    linked_products = []

                    # 1. جلب جميع البرامج النشطة التي تعطي هدايا من نوع product
                    programs = env['loyalty.program'].sudo().search([('active', '=', True)])
                    for prog in programs:
                        for reward in prog.reward_ids:
                            if reward.reward_type == 'product' and prod_obj in reward.reward_product_ids:
                                # هذا البرنامج يعطي هذا المنتج كهدية
                                # فحص الـ rules لمعرفة المنتجات الأصلية
                                for rule in prog.rule_ids:
                                    for orig_product in rule.product_ids:
                                        prod_name_str = orig_product.display_name or orig_product.name
                                        if orig_product not in linked_products:
                                            linked_products.append(prod_name_str)

                    if linked_products:
                        vals['name'] = f"{prod_name} (هدية مجانية)"
                    else:
                        vals['name'] = f"{prod_name} (هدية مجانية)"

                SOL.create(vals)
            # ==============================================================

            msl_saved, msl_via = self._save_msl_results(env, so, msl_results)

            # تم حذف self._apply_mobile_rewards(env, so, reward_items)

            # if so.state in ('draft', 'sent'):
            #     so.action_confirm()

            resp = {
                "sale_order": {
                    "id": so.id,
                    "name": noneify(so.name),
                    "state": noneify(so.state),
                    "warehouse_id": wh.id,
                    "warehouse_name": noneify(wh.name),
                },
                "msl_results_saved": int(msl_saved),
                "msl_saved_via": noneify(msl_via),
            }
            return format_response(
                True,
                "Sale order created and confirmed (no delivery/invoice/payment).",
                resp,
                http_status=200
            )

        except Exception as e:
            _logger.exception("CashVan SO Create API error")
            return format_response(False, f"Internal error: {str(e)}", error_code=-500, http_status=500)

    # -----------------------------
    # CashVan: Deliver existing SO (no invoice/payment)
    # -----------------------------
    @http.route(
        ['/sales_rep_manager/<string:api_version>/cashvan/so/deliver'],
        type='http', auth='none', methods=['POST', 'OPTIONS'], csrf=False, cors='*'
    )
    @jwt_required()
    def cashvan_so_deliver(self, **kwargs):
        if request.httprequest.method == 'OPTIONS':
            return json_response({"ok": True}, status=200)

        env = kwargs["_jwt_env"]
        current_user = env['res.users'].browse(kwargs["_jwt_user_id"])

        try:
            body, error = self._get_body()
            if error:
                return format_response(False, error, error_code=-100, http_status=400)

            so_id = body.get('sale_order_id')
            so_name = body.get('sale_order_name')

            SaleOrder = env['sale.order'].sudo()

            if so_id:
                so = SaleOrder.browse(int(so_id))
            elif so_name:
                so = SaleOrder.search([('name', '=', so_name)], limit=1)
            else:
                return format_response(
                    False,
                    "sale_order_id or sale_order_name is required",
                    error_code=-101,
                    http_status=400
                )

            if not so or not so.exists():
                return format_response(False, "Sale order not found", error_code=-102, http_status=404)

            RepProfile = env['sales.rep.profile'].sudo()
            rep_profile = RepProfile.search([('user_id', '=', current_user.id)], limit=1)
            if not rep_profile or not rep_profile.location_id:
                return format_response(
                    False,
                    "No location assigned to this sales representative",
                    error_code=-404,
                    http_status=400
                )
            rep_loc = rep_profile.location_id

            Warehouse = env['stock.warehouse'].sudo()
            wh = so.warehouse_id or Warehouse.search(
                [('company_id', '=', current_user.company_id.id)], limit=1
            )

            if so.state in ('draft', 'sent'):
                so.action_confirm()

            delivered_picking_ids = []
            for p in so.picking_ids.sudo().filtered(lambda r: r.picking_type_code == 'outgoing'):
                if p.state in ('done', 'cancel'):
                    continue

                self._apply_rep_outgoing_type(env, p, rep_profile, rep_loc, wh)

                if p.state == 'draft':
                    p.action_confirm()

                ok = self._validate_picking(env, p)
                _logger.info("CashVan SO Deliver: picking %s validated=%s", p.name, ok)
                if p.state == 'done':
                    delivered_picking_ids.append(p.id)

            resp = {
                "sale_order": {
                    "id": so.id,
                    "name": noneify(so.name),
                    "state": noneify(so.state),
                    "invoice_status": noneify(so.invoice_status),
                },
                "delivered_picking_ids": delivered_picking_ids,
            }
            return format_response(True, "Sale order confirmed and deliveries processed.", resp, http_status=200)

        except Exception as e:
            _logger.exception("CashVan SO Deliver API error")
            return format_response(False, f"Internal error: {str(e)}", error_code=-500, http_status=500)

    # -----------------------------
    # CashVan: Invoice & Pay for SO or existing Invoice
    # -----------------------------
    @http.route(
        ['/sales_rep_manager/<string:api_version>/cashvan/so/invoice_pay'],
        type='http', auth='none', methods=['POST', 'OPTIONS'], csrf=False, cors='*'
    )
    @jwt_required()
    def cashvan_so_invoice_pay(self, **kwargs):
        if request.httprequest.method == 'OPTIONS':
            return json_response({"ok": True}, status=200)

        env = kwargs["_jwt_env"]
        current_user = env['res.users'].browse(kwargs["_jwt_user_id"])

        try:
            body, error = self._get_body()
            if error:
                return format_response(False, error, error_code=-100, http_status=400)

            so_id = body.get('sale_order_id')
            so_name = body.get('sale_order_name')

            inv_id = body.get('invoice_id')
            inv_name = body.get('invoice_name')

            mobile_invoice_number = body.get('mobile_invoice_number')

            payment = body.get('payment') or {}
            pay_amount = payment.get('amount')
            pay_date = payment.get('payment_date') or payment.get('date')
            pay_currency_val = payment.get('currency')
            pay_currency_id = payment.get('currency_id')
            pay_currency_code = payment.get('currency_code') or payment.get('currency')

            SaleOrder = env['sale.order'].sudo()
            AccountMove = env['account.move'].sudo()

            inv = None
            so = None

            if so_id or so_name:
                if so_id:
                    so = SaleOrder.browse(int(so_id))
                else:
                    so = SaleOrder.search([('name', '=', so_name)], limit=1)

                if not so or not so.exists():
                    return format_response(False, "Sale order not found", error_code=-101, http_status=404)

                try:
                    so._compute_invoice_status()
                except Exception:
                    pass

                invoices = AccountMove.browse([])
                try:
                    invoices = so._create_invoices(final=False)
                except Exception:
                    invoices = AccountMove.browse([])

                if not invoices:
                    if 'sale.advance_payment.inv' not in env:
                        return format_response(
                            False,
                            "Invoicing wizard not available (sale.advance_payment.inv).",
                            error_code=-201,
                            http_status=400
                        )
                    wiz = env['sale.advance_payment.inv'].sudo().create({'advance_payment_method': 'delivered'})
                    wiz = wiz.with_context(active_model='sale.order', active_ids=[so.id], open_invoices=False)
                    pre = so.invoice_ids.ids
                    wiz.create_invoices()
                    so.flush()
                    new_ids = [i for i in so.invoice_ids.ids if i not in pre]
                    invoices = AccountMove.browse(new_ids)

                if not invoices:
                    return format_response(
                        False,
                        "Cannot create an invoice. No items are available to invoice.",
                        error_code=-202,
                        http_status=400
                    )

                inv = invoices[:1]

                if mobile_invoice_number:
                    inv.sudo().write({'mobile_invoice_number': mobile_invoice_number})

                if inv.state == 'draft':
                    inv.action_post()

            elif inv_id or inv_name:
                if inv_id:
                    inv = AccountMove.browse(int(inv_id))
                else:
                    inv = AccountMove.search([('name', '=', inv_name)], limit=1)

                if not inv or not inv.exists():
                    return format_response(False, "Invoice not found", error_code=-102, http_status=404)

                if inv.state != 'posted':
                    return format_response(
                        False,
                        "Invoice must be posted before payment.",
                        error_code=-103,
                        http_status=400
                    )
            else:
                return format_response(
                    False,
                    "sale_order_id/sale_order_name or invoice_id/invoice_name is required",
                    error_code=-104,
                    http_status=400
                )

            RepProfile = env['sales.rep.profile'].sudo()
            rep_profile = RepProfile.search([('user_id', '=', current_user.id)], limit=1)
            if not rep_profile:
                return format_response(
                    False,
                    "Sales rep profile not found for this user.",
                    error_code=-301,
                    http_status=400
                )

            inv_date = getattr(inv, 'invoice_date', None) or getattr(inv, 'date', None)
            if not pay_date and inv_date:
                pay_date = inv_date

            fallback_cur = inv.currency_id or (current_user.company_id and current_user.company_id.currency_id)
            pay_currency = self._resolve_currency(
                env,
                pay_currency_val,
                cur_id=pay_currency_id,
                cur_code=pay_currency_code,
                fallback=fallback_cur
            )
            if not pay_currency:
                return format_response(False, "Currency not found.", error_code=-204, http_status=400)

            journal = self._get_rep_journal_for_currency(env, rep_profile, pay_currency)
            if not journal:
                return format_response(
                    False,
                    "No cash journal mapped for this user & currency. Please configure it in the Sales Rep Profile.",
                    error_code=-305,
                    http_status=400
                )

            if inv.state != 'posted':
                return format_response(
                    False,
                    "Invoice must be posted before payment.",
                    error_code=-103,
                    http_status=400
                )

            ctx = {'active_model': 'account.move', 'active_ids': [inv.id]}
            Register = env['account.payment.register'].with_context(ctx).sudo()
            reg_vals = {
                'journal_id': journal.id,
                'amount': float(pay_amount) if pay_amount is not None else inv.amount_residual,
            }
            if pay_date:
                reg_vals['payment_date'] = pay_date
            reg = Register.create(reg_vals)
            reg.action_create_payments()

            resp = {
                "sale_order": None if not so else {
                    "id": so.id,
                    "name": noneify(so.name),
                    "state": noneify(so.state),
                    "invoice_status": noneify(so.invoice_status),
                },
                "invoice": {
                    "id": inv.id,
                    "name": noneify(inv.name),
                    "state": noneify(inv.state),
                    "payment_state": noneify(inv.payment_state),
                    "mobile_invoice_number": noneify(getattr(inv, 'mobile_invoice_number', None)),
                    "amount_total": inv.amount_total,
                    "amount_residual": inv.amount_residual,
                },
                "journal_used": {
                    "id": journal.id,
                    "name": noneify(journal.name),
                    "currency": noneify(
                        journal.currency_id.name or (
                            journal.company_id.currency_id.name if journal.company_id else None
                        )
                    ),
                },
                "payment_date": noneify(pay_date),
            }
            return format_response(True, "Invoice created (if SO given) and paid successfully.", resp, http_status=200)

        except Exception as e:
            _logger.exception("CashVan SO Invoice+Pay API error")
            return format_response(False, f"Internal error: {str(e)}", error_code=-500, http_status=500)

    # -----------------------------
    # CashVan: Manual payment (no invoice)
    # -----------------------------
    @http.route(
        ['/sales_rep_manager/<string:api_version>/cashvan/payment'],
        type='http', auth='none', methods=['POST', 'OPTIONS'], csrf=False, cors='*'
    )
    @jwt_required()
    def cashvan_payment_manual(self, **kwargs):
        if request.httprequest.method == 'OPTIONS':
            return json_response({"ok": True}, status=200)

        env = kwargs["_jwt_env"]
        current_user = env['res.users'].browse(kwargs["_jwt_user_id"])

        try:
            body, error = self._get_body()
            if error:
                return format_response(False, error, error_code=-100, http_status=400)

            # Partner ID يتم جلبه مرة واحدة لأنه مشترك لكل الدفعات
            partner_id = body.get('partner_id')
            if isinstance(partner_id, dict):
                partner_id = partner_id.get('id')
            if not partner_id:
                return format_response(False, "partner_id is required", error_code=-101, http_status=400)

            Partner = env['res.partner'].sudo()
            partner = Partner.browse(int(partner_id))
            if not partner or not partner.exists():
                return format_response(False, "Partner not found", error_code=-105, http_status=404)

            RepProfile = env['sales.rep.profile'].sudo()
            rep_profile = RepProfile.search([('user_id', '=', current_user.id)], limit=1)
            if not rep_profile:
                return format_response(
                    False,
                    "Sales rep profile not found for this user.",
                    error_code=-301,
                    http_status=400
                )

            # ==================== التعديل هنا: استقبال البيانات كقائمة ====================
            # ندعم الحالتين: إما يرسل key اسمه payments يحتوي قائمة، أو payment يحتوي قاموس
            raw_payments = body.get('payments') or body.get('payment') or []

            # إذا وصل قاموس واحد (Object) نحوله لقائمة لتوحيد التعامل
            payment_list = []
            if isinstance(raw_payments, list):
                payment_list = raw_payments
            elif isinstance(raw_payments, dict):
                payment_list = [raw_payments]

            if not payment_list:
                # يمكنك إرجاع خطأ هنا أو إكمال التنفيذ وإرجاع قائمة فارغة حسب رغبتك
                # سأتركها ترجع خطأ إذا لم توجد أي بيانات للدفع لضمان سلامة الطلب
                return format_response(False, "No payment data provided", error_code=-102, http_status=400)

            AccountPayment = env['account.payment'].sudo()

            # قائمة لتجميع النتائج النهائية
            results_data = []

            # الدوران على قائمة الدفعات
            for payment in payment_list:
                if not isinstance(payment, dict):
                    continue

                pay_amount = payment.get('amount')
                pay_date = payment.get('payment_date') or payment.get('date')
                pay_currency_val = payment.get('currency')
                pay_currency_id = payment.get('currency_id')
                pay_currency_code = payment.get('currency_code') or payment.get('currency')

                memo_text = payment.get('memo') or payment.get('note') or None

                if pay_amount is None:
                    return format_response(False, "payment.amount is required for all items", error_code=-102,
                                           http_status=400)

                try:
                    pay_amount = float(pay_amount)
                except Exception:
                    return format_response(False, "payment.amount must be a number", error_code=-103, http_status=400)

                if pay_amount <= 0:
                    return format_response(False, "payment.amount must be > 0", error_code=-104, http_status=400)

                fallback_cur = current_user.company_id.currency_id if current_user.company_id else None
                pay_currency = self._resolve_currency(
                    env,
                    pay_currency_val,
                    cur_id=pay_currency_id,
                    cur_code=pay_currency_code,
                    fallback=fallback_cur
                )
                if not pay_currency:
                    return format_response(False, "Currency not found.", error_code=-204, http_status=400)

                # ALWAYS: journal currency = payment currency
                # يتم جلب الجورنال داخل اللوب لأن العملة قد تختلف من دفعة لأخرى
                journal = self._get_rep_journal_for_currency(env, rep_profile, pay_currency)
                if not journal:
                    return format_response(
                        False,
                        f"No cash journal mapped for this sales rep and currency ({pay_currency.name}).",
                        error_code=-305,
                        http_status=400
                    )

                if not pay_date:
                    pay_date = fields.Date.context_today(env.user)

                vals = {
                    'payment_type': 'inbound',
                    'partner_type': 'customer',
                    'partner_id': partner.id,
                    'amount': pay_amount,
                    'currency_id': pay_currency.id,
                    'date': pay_date,
                    'journal_id': journal.id,
                    'company_id': current_user.company_id.id if current_user.company_id else False,
                }
                if memo_text:
                    vals['payment_reference'] = memo_text

                payment_rec = AccountPayment.create(vals)

                if hasattr(payment_rec, 'action_post') and payment_rec.state == 'draft':
                    payment_rec.action_post()

                # تجهيز نتيجة الدفعة الحالية
                single_resp = {
                    "payment": {
                        "id": payment_rec.id,
                        "name": noneify(getattr(payment_rec, 'name', None)),
                        "state": noneify(getattr(payment_rec, 'state', None)),
                        "payment_type": noneify(payment_rec.payment_type),
                        "partner_type": noneify(payment_rec.partner_type),
                        "partner_id": partner.id,
                        "partner_name": noneify(partner.display_name),
                        "amount": payment_rec.amount,
                        "currency": {
                            "id": payment_rec.currency_id.id,
                            "name": noneify(payment_rec.currency_id.name),
                        } if payment_rec.currency_id else None,
                        "date": noneify(str(payment_rec.date)),
                        "payment_reference": noneify(getattr(payment_rec, 'payment_reference', None)),
                    },
                    "journal_used": {
                        "id": journal.id,
                        "name": noneify(journal.name),
                        "type": noneify(journal.type),
                        "currency": noneify(
                            journal.currency_id.name or (
                                journal.company_id.currency_id.name if journal.company_id else None
                            )
                        ),
                    },
                }

                # إضافة النتيجة للقائمة
                results_data.append(single_resp)

            # إرجاع كافة النتائج
            final_response = {
                "count": len(results_data),
                "payments": results_data
            }
            return format_response(True, "Manual payments created successfully.", final_response, http_status=200)

        except Exception as e:
            _logger.exception("CashVan manual payment API error")
            return format_response(False, f"Internal error: {str(e)}", error_code=-500, http_status=500)
