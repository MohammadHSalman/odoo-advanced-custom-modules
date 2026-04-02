# controllers/sale_orders_workflows_api.py
# -*- coding: utf-8 -*-
import logging
from odoo import http
from odoo.http import request
from .api_utils import json_response, jwt_required, format_response, noneify

_logger = logging.getLogger(__name__)


class SaleOrdersWorkflowsAPI(http.Controller):

    # ---------- Helpers ----------
    def _preflight(self):
        if request.httprequest.method == 'OPTIONS':
            return json_response({"ok": True}, status=200)
        return None

    def _get_body(self):
        """Parse JSON body safely for type='http' routes."""
        try:
            data = request.get_json_data() or {}
            if not isinstance(data, dict):
                return None, "Invalid JSON: body must be an object"
            return data, None
        except Exception:
            return None, "Invalid JSON body"

    def _serialize_order(self, order, with_lines=True):
        lines = []
        if with_lines:
            for l in order.order_line:
                prod = l.product_id
                uom = l.product_uom
                taxes = [
                    {
                        "id": t.id,
                        "name": noneify(t.name),
                        "amount": t.amount,
                        "type": t.amount_type
                    } for t in l.tax_id
                ]
                lines.append({
                    "line_id": l.id,
                    "product_id": prod.id if prod else None,
                    "product_name": noneify(getattr(prod, "display_name", None)),
                    "quantity": l.product_uom_qty,
                    "uom": noneify(getattr(uom, "display_name", None)),
                    "price_unit": l.price_unit,
                    "discount": l.discount,            # %
                    "subtotal": l.price_subtotal,      # بدون ضريبة
                    "tax": l.price_tax,                # قيمة الضريبة
                    "total": l.price_total,            # مع الضريبة
                    "qty_delivered": getattr(l, 'qty_delivered', None),
                    "qty_to_invoice": getattr(l, 'qty_to_invoice', None),
                    "invoice_status": getattr(l, 'invoice_status', None),
                    "taxes": taxes,
                    "name": noneify(l.name),
                })

        partner = order.partner_id
        currency = order.currency_id
        user = order.user_id

        data = {
            "id": order.id,
            "name": noneify(order.name),
            "partner_id": partner.id if partner else None,
            "partner_name": noneify(getattr(partner, "name", None)),
            "date_order": order.date_order.strftime('%Y-%m-%d %H:%M:%S') if order.date_order else None,
            "currency": noneify(getattr(currency, "name", None)),
            "amount_untaxed": order.amount_untaxed,
            "amount_tax": order.amount_tax,
            "amount_total": order.amount_total,
            "state": order.state,                      # draft/sent/sale/done/cancel
            "invoice_status": order.invoice_status,    # no/to invoice/invoiced
            "user": (
                {"id": user.id, "name": noneify(user.name)}
                if user else None
            ),
            "lines_count": len(lines),
            "lines": lines,
        }
        return data

    def _ensure_confirmed(self, order):
        """حوّل الطلب إلى sale إن لم يكن sale/done."""
        if order.state not in ('sale', 'done'):
            order.action_confirm()
        return order.state in ('sale', 'done')

    def _deliver_all_pickings(self, env, order):
        """
        تسليم كل شحنات الطلب (خروج) بدون stock.immediate.transfer:
          - action_view_delivery()
          - تأكيد/حجز
          - تعبئة qty_done (move lines) / quantity_done (moves)
          - button_validate()
          - معالجة Backorder إن ظهر
        """
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
            try:
                p.action_assign()
            except Exception:
                pass

            # move lines -> qty_done
            if p.move_line_ids:
                for ml in p.move_line_ids:
                    if (ml.quantity or 0.0) <= 0.0:
                        ml.quantity = ml.product_uom_qty or ml.reserved_uom_qty or 0.0
            else:
                # moves -> quantity_done
                for mv in p.move_ids_without_package:
                    if (mv.quantity or 0.0) <= 0.0:
                        mv.quantity = mv.product_uom_qty

            if hasattr(p, 'immediate_transfer'):
                p.immediate_transfer = True

            res = p.button_validate()

            # Backorder wizard
            if isinstance(res, dict) and res.get('res_model') == 'stock.backorder.confirmation':
                wiz = env['stock.backorder.confirmation'].sudo().browse(res.get('res_id', 0))
                if not wiz or not wiz.exists():
                    wiz = env['stock.backorder.confirmation'].sudo().create({'pick_ids': [(4, p.id)]})
                wiz.process()

            if p.state == 'done':
                delivered.append(p.id)

        return delivered

    # ======================================================
    # 1) GET: كل الطلبات غير المفوترة نهائياً (invoice_status != 'invoiced')
    # ======================================================
    @http.route('/sales_rep_manager/<string:api_version>/sale_orders',
                type='http', auth='none', methods=['GET', 'OPTIONS'], csrf=False, cors="*")
    @jwt_required()
    def list_not_fully_invoiced_orders(self, **kwargs):
        """
        يُرجع طلبات البيع التي ليست مفوترة نهائياً (invoice_status != 'invoiced')
        - بدون قبول أي بارامترات من العميل.
        - مقيّدة بطلبات المستخدم الحالي فقط.
        - تُعيد السطور كاملة.
        """
        pre = self._preflight()
        if pre:
            return pre
        try:
            env = kwargs["_jwt_env"]
            current_user_id = kwargs["_jwt_user_id"]
            SaleOrder = env['sale.order'].sudo()

            domain = [
                ('invoice_status', '!=', 'invoiced'),
                ('user_id', '=', current_user_id),
            ]
            order = 'date_order desc, id desc'

            sale_orders = SaleOrder.search(domain, order=order)
            orders_list = [self._serialize_order(o, with_lines=True) for o in sale_orders]

            return format_response(True, "Sale orders (invoice_status != 'invoiced') fetched successfully", {
                "filters": {
                    "exclude_invoice_status": "invoiced",
                    "only_my": True,
                },
                "total": len(sale_orders),
                "sale_orders": orders_list
            }, http_status=200)

        except Exception as e:
            _logger.exception("Error fetching sale orders (invoice_status != invoiced)")
            return format_response(False, f"Internal error: {str(e)}", error_code=-500, http_status=500)

    # =====================================================================
    # 2) POST: جعل طلب محدد "طلب مفوتر"
    # =====================================================================
    @http.route('/sales_rep_manager/<string:api_version>/sale_orders/<int:order_id>/bill',
                type='http', auth='none', methods=['POST', 'OPTIONS'], csrf=False, cors="*")
    @jwt_required()
    def bill_existing_order(self, order_id, **kwargs):
        """
        يجعل الطلب المختار "طلب مفوتر" بنفس منطق الإنشاء:
          - تأكيد الطلب إن لزم
          - تسليم الشحنات outgoing (اختياري deliver=true)
          - إنشاء فاتورة بطريقة delivered (مع فولباك الويزارد)
          - تأكيد الفاتورة (اختياري post=true)

        Body (اختياري):
        {
          "order_status": "invoiced",   // إن أُرسلت يجب أن تكون 'invoiced' أو 'طلب مفوتر'
          "deliver": true,              // افتراضي true: نفّذ التسليم قبل الفوترة
          "post": true,                 // افتراضي true: أكّد الفاتورة بعد الإنشاء
          "with_lines": false,          // افتراضي false: أعد سطور الطلب في الاستجابة
          "mobile_invoice_number": "MOB-INV-12345"  // NEW
        }
        """
        pre = self._preflight()
        if pre:
            return pre
        try:
            env = kwargs["_jwt_env"]

            body, err = self._get_body()
            if err:
                body = {}

            # NEW: رقم فاتورة الموبايل (إن وُجد)
            mobile_invoice_number = body.get('mobile_invoice_number') or body.get('mobile_local_number') or body.get(
                'mobile_number')

            # إن تم إرسال order_status نتحقق أنه مفوتر
            requested_status_raw = (body.get('order_status') or body.get('status') or body.get('state') or '').strip()
            if requested_status_raw:
                status_map = {
                    'invoiced': 'invoiced', 'invoice': 'invoiced', 'billed': 'invoiced',
                    'طلب مفوتر': 'invoiced', 'مفوتر': 'invoiced',
                    'confirmed': 'confirmed', 'confirm': 'confirmed', 'sale': 'confirmed',
                    'طلب مؤكد': 'confirmed', 'مؤكد': 'confirmed',
                }
                normalized = status_map.get(requested_status_raw.lower(), None)
                if normalized != 'invoiced':
                    return format_response(
                        False,
                        "To bill an order you must send order_status='طلب مفوتر' (or 'invoiced'), if you send order_status at all.",
                        error_code=-103,
                        data={"received": requested_status_raw or None},
                        http_status=400
                    )

            # خيارات اختيارية
            deliver_first = bool(body.get('deliver', True))
            post_invoice = bool(body.get('post', True))
            with_lines = bool(body.get('with_lines', False))

            SaleOrder = env['sale.order'].sudo()
            so = SaleOrder.browse(order_id)
            if not so.exists():
                return format_response(False, "Sale order not found", error_code=-404, http_status=404)

            workflow = {
                "order_id": so.id,
                "order_state_before": so.state,
                "confirmed": False,
                "delivered_picking_ids": [],
                "invoices_created": 0,
                "invoice_ids": [],
            }

            # 1) تأكيد الطلب
            workflow["confirmed"] = self._ensure_confirmed(so)

            # 2) تسليم الشحنات
            if deliver_first:
                workflow["delivered_picking_ids"] = self._deliver_all_pickings(env, so)

            # 3) تحديث حالة الفوترة والتحقّق من وجود سطور قابلة للفوترة
            try:
                so._compute_invoice_status()
            except Exception:
                pass

            if hasattr(so, '_get_invoiceable_lines'):
                try:
                    invoiceable_lines = so._get_invoiceable_lines(final=False)
                except Exception:
                    invoiceable_lines = so.order_line.filtered(
                        lambda l: (getattr(l, 'qty_to_invoice', 0.0) or 0.0) > 0)
            else:
                invoiceable_lines = so.order_line.filtered(
                    lambda l: (getattr(l, 'qty_to_invoice', 0.0) or 0.0) > 0)

            if not invoiceable_lines:
                diag = {
                    "order_state": so.state,
                    "invoice_status": so.invoice_status,
                    "lines": [
                        {
                            "line_id": l.id,
                            "product": noneify(getattr(l.product_id, 'display_name', None)),
                            "qty_ordered": l.product_uom_qty,
                            "qty_delivered": getattr(l, 'qty_delivered', None),
                            "qty_to_invoice": getattr(l, 'qty_to_invoice', None),
                            "invoice_status": getattr(l, 'invoice_status', None),
                        } for l in so.order_line
                    ],
                    "pickings": [
                        {
                            "id": p.id,
                            "name": noneify(p.name),
                            "state": p.state,
                            "done_moves": sum(mv.quantity for mv in p.move_ids_without_package),
                        } for p in so.picking_ids
                    ],
                }
                return format_response(
                    False,
                    "Cannot create invoice: no invoiceable lines (most likely nothing delivered yet with delivered policy).",
                    error_code=-202,
                    data=diag,
                    http_status=200
                )

            # 4) إنشاء الفاتورة مباشرة
            AccountMove = env['account.move'].sudo()
            invoices = AccountMove.browse([])
            try:
                invoices = so._create_invoices(final=False)
            except Exception:
                invoices = AccountMove.browse([])

            # فولباك الويزارد (delivered) إن لزم
            if not invoices:
                if 'sale.advance.payment.inv' not in env:
                    return format_response(False, "Invoicing wizard not available (sale.advance.payment.inv).",
                                           error_code=-201, http_status=200)
                wiz = env['sale.advance.payment.inv'].sudo().create({'advance_payment_method': 'delivered'})
                wiz = wiz.with_context(active_model='sale.order', active_ids=[so.id], open_invoices=False)
                pre_ids = so.invoice_ids.ids
                try:
                    wiz.create_invoices()
                except Exception:
                    return format_response(False, "Create invoices failed.", error_code=-202, http_status=200)
                so.flush()
                new_ids = [i for i in so.invoice_ids.ids if i not in pre_ids]
                invoices = AccountMove.browse(new_ids)

            # 5) تأكيد الفواتير
            if post_invoice and invoices:
                to_post = invoices.filtered(lambda m: m.state == 'draft')
                if to_post:
                    to_post.action_post()

            # NEW: كتابة رقم فاتورة الموبايل على الفواتير المنشأة
            if mobile_invoice_number and invoices:
                invoices.sudo().write({'mobile_invoice_number': mobile_invoice_number})

            workflow["invoices_created"] = len(invoices)
            workflow["invoice_ids"] = invoices.ids

            # إخراج
            return format_response(True, "Sale order billed successfully", {
                "order": self._serialize_order(so, with_lines=with_lines),
                "workflow": workflow,
                "invoices": [{
                    "id": inv.id,
                    "name": noneify(inv.name),
                    "state": inv.state,
                    "move_type": inv.move_type,
                    "amount_total": inv.amount_total,
                    "currency": noneify(getattr(inv.currency_id, "name", None)),
                    # NEW: إظهار رقم فاتورة الموبايل
                    "mobile_invoice_number": noneify(getattr(inv, 'mobile_invoice_number', None)),
                } for inv in invoices] if invoices else None
            }, http_status=200)

        except Exception as e:
            _logger.exception("Error billing sale order")
            return format_response(False, f"Internal error: {str(e)}", error_code=-500, http_status=500)
