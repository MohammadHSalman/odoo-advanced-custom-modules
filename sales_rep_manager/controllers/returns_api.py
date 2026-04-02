# -*- coding: utf-8 -*-
import logging
from odoo import http, fields, SUPERUSER_ID
from odoo.http import request
from .api_utils import json_response, jwt_required, format_response, noneify

_logger = logging.getLogger(__name__)


class ReturnsAPI(http.Controller):

    # ----------------------------------------------------------------------
    # Helpers (نفس نمطك)
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
    # Direct Customer Return: customer → sales rep location (no sale order)
    # ----------------------------------------------------------------------
    @http.route(
        '/sales_rep_manager/<string:api_version>/returns/direct',
        type='http', auth='none', methods=['POST', 'OPTIONS'], csrf=False, cors='*'
    )
    @jwt_required()
    def create_direct_customer_return(self, **kwargs):
        # CORS preflight
        if request.httprequest.method == 'OPTIONS':
            return json_response({"ok": True}, status=200)

        try:
            env = kwargs["_jwt_env"]
            current_user = env['res.users'].browse(kwargs["_jwt_user_id"])

            data, error = self._get_body()
            if error:
                return format_response(False, error, error_code=-100, http_status=400)

            partner_id = data.get('partner_id')
            lines = data.get('lines') or []
            if not partner_id:
                return format_response(False, "Missing required parameter: partner_id", error_code=-101,
                                       http_status=400)
            if not lines or not isinstance(lines, list):
                return format_response(False, "Missing or invalid 'lines': must be a non-empty list", error_code=-102,
                                       http_status=400)

            # Models
            Partner = env['res.partner'].sudo()
            Picking = env['stock.picking'].sudo()
            PickingType = env['stock.picking.type'].sudo()
            Product = env['product.product'].sudo()
            StockLocation = env['stock.location'].sudo()
            RepProfile = env['sales.rep.profile'].sudo()

            partner = Partner.browse(int(partner_id))
            if not partner.exists():
                return format_response(False, f"partner_id {partner_id} not found", error_code=-103, http_status=404)

            # المصدر: موقع الزبائن
            src_loc = partner.property_stock_customer or env.ref('stock.stock_location_customers',
                                                                 raise_if_not_found=False)
            if not src_loc:
                return format_response(False, "Customer source location not resolvable.", error_code=-107,
                                       http_status=400)

            # الوجهة: موقع المندوب من بروفايله (إلزامي في هذه المرحلة)
            rep_profile = RepProfile.search([
                ('user_id', '=', current_user.id),
                ('company_id', '=', current_user.company_id.id if current_user.company_id else False),
            ], limit=1)
            if not rep_profile or not rep_profile.location_id:
                return format_response(False, "sales.rep.profile is missing or has no location_id for this user.",
                                       error_code=-108, http_status=400)
            dest_loc = rep_profile.location_id

            # نوع الشحنة: حسب طلبك صراحة picking_type_id = 1
            picking_type = PickingType.browse(1)
            if not picking_type.exists():
                return format_response(False, "Configured picking_type_id=1 not found.", error_code=-109,
                                       http_status=400)

            note = (data.get('note') or '').strip()

            # سطور الحركة + تجميع ملاحظات التوالف بالأسماء
            move_cmds, damaged_notes = [], []
            for idx, l in enumerate(lines, start=1):
                pid = l.get('product_id')
                qty = l.get('quantity') or l.get('product_uom_qty')  # دعم كلا الاسمين
                if not pid:
                    return format_response(False, f"Line #{idx}: missing product_id", error_code=-110, http_status=400)
                try:
                    qty = float(qty)
                except Exception:
                    return format_response(False, f"Line #{idx}: quantity must be a number", error_code=-111,
                                           http_status=400)
                if qty <= 0:
                    return format_response(False, f"Line #{idx}: quantity must be > 0", error_code=-112,
                                           http_status=400)

                product = Product.browse(int(pid))
                if not product.exists():
                    return format_response(False, f"Line #{idx}: product_id {pid} not found", error_code=-113,
                                           http_status=404)

                move_cmds.append((0, 0, {
                    'name': product.display_name,
                    'product_id': product.id,
                    'product_uom_qty': qty,
                    'product_uom': product.uom_id.id,
                    'location_id': src_loc.id,
                    'location_dest_id': dest_loc.id,
                }))

                if l.get('damaged') is True:
                    damaged_notes.append(f"- {product.display_name}: {qty}")

            if damaged_notes:
                dmg_text = "Damaged items:\n" + "\n".join(damaged_notes)
                note = f"{note}\n{dmg_text}".strip() if note else dmg_text

            # إنشاء الشحنة حسب حقولك المطلوبة حرفيًا
            picking_vals = {
                'partner_id': partner.id,  # الزبون
                'picking_type_id': picking_type.id,  # == 1
                'location_id': src_loc.id,
                'location_dest_id': dest_loc.id,  # من بروفايل المندوب
                'origin': 'Direct Customer Return',
                'move_ids_without_package': move_cmds,  # product_id + product_uom_qty
                'note': note or False,  # ملاحظات (التوالف بالاسم)
            }
            picking = Picking.create(picking_vals)

            # اعتماد الشحنة: نضبط qty_done = product_uom_qty ثم validate
            try:
                picking.action_confirm()
            except Exception:
                pass

            # مهم: التعيين قد لا يكون ضروريًا لوارد من عميل، لكن لا يضر
            try:
                picking.action_assign()
            except Exception:
                pass

            # اضبط الكميات المنجزة على مستوى move (أسهل وأضمن)
            # قبل التحقق عيّن الكميات المنجزة بشكل صحيح:
            for mv in picking.move_ids_without_package:
                mv.quantity = mv.product_uom_qty  # ✅ مش quantity

            # نفّذ التحقق كسوبر يوزر + ثبّت الـ location في الكونتكست
            ctx = dict(env.context, skip_backorder=True, location=dest_loc.id, warehouse=False)
            res = picking.with_user(SUPERUSER_ID).with_context(ctx).button_validate()

            # في حال رجّع معالج Backorder
            if isinstance(res, dict) and res.get('res_model') == 'stock.backorder.confirmation':
                wiz = env['stock.backorder.confirmation'].sudo().browse(res.get('res_id', 0))
                if not wiz or not wiz.exists():
                    wiz = env['stock.backorder.confirmation'].sudo().create({'pick_ids': [(4, picking.id)]})
                wiz.process()

            # إخراج مبسّط
            picking_out = {
                "id": picking.id,
                "name": picking.name,
                "state": picking.state,
                "picking_type_id": picking.picking_type_id.id,
                "partner": getattr(picking.partner_id, "display_name", None),
                "location_src": getattr(picking.location_id, "display_name", None),
                "location_dest": getattr(picking.location_dest_id, "display_name", None),
                "note": picking.note or "",
                "moves": [{
                    "id": m.id,
                    "product": getattr(m.product_id, "display_name", None),
                    "uom": getattr(m.product_uom, "name", None),
                    "qty_demand": m.product_uom_qty,
                    "qty_done": m.quantity,
                    "state": m.state,
                } for m in picking.move_ids_without_package],
            }

            return format_response(True, "Direct return created & validated.", {
                "return_picking": picking_out
            }, http_status=200)

        except Exception as e:
            _logger.exception("Error while creating direct return (phase 1)")
            return format_response(False, f"Internal error: {str(e)}", error_code=-500, http_status=500)

    # ------------------------------------------------------------
    # Phase 2: إنشاء فاتورة مرتجع (Credit Note) باسم الزبون
    # ------------------------------------------------------------
    # ------------------------------------------------------------
    # Phase 2: إنشاء فاتورة مرتجع (Credit Note) باسم الزبون
    # ------------------------------------------------------------
    @http.route(
        '/sales_rep_manager/<string:api_version>/returns/credit',
        type='http', auth='none', methods=['POST', 'OPTIONS'], csrf=False, cors='*'
    )
    @jwt_required()
    def create_credit_note_phase2(self, **kwargs):
        # CORS preflight
        if request.httprequest.method == 'OPTIONS':
            return json_response({"ok": True}, status=200)

        try:
            env = kwargs["_jwt_env"]
            current_user = env['res.users'].browse(kwargs["_jwt_user_id"])

            # جسم الطلب
            data, error = self._get_body()
            if error:
                return format_response(False, error, error_code=-100, http_status=400)

            # مطلوب
            partner_id = data.get('partner_id')
            lines = data.get('lines') or []
            if not partner_id:
                return format_response(False, "Missing required parameter: partner_id", error_code=-101,
                                       http_status=400)
            if not lines or not isinstance(lines, list):
                return format_response(False, "Missing or invalid 'lines': must be a non-empty list", error_code=-102,
                                       http_status=400)

            # اختياري
            note = (data.get('note') or '').strip()
            currency_id = data.get('currency_id')
            journal_id = data.get('journal_id') or data.get('refund_journal_id')
            invoice_origin = data.get('invoice_origin') or data.get('origin')

            # موديلات
            Partner = env['res.partner'].sudo()
            Product = env['product.product'].sudo()
            AccountMove = env['account.move'].sudo()

            partner = Partner.browse(int(partner_id))
            if not partner.exists():
                return format_response(False, f"partner_id {partner_id} not found", error_code=-103, http_status=404)

            # بناء invoice_line_ids — السعر يؤخذ دومًا من المنتج نفسه (lst_price)
            invoice_line_cmds = []
            for idx, l in enumerate(lines, start=1):
                pid = l.get('product_id')
                qty = l.get('quantity')
                if not pid:
                    return format_response(False, f"Line #{idx}: missing product_id", error_code=-110, http_status=400)
                try:
                    qty = float(qty)
                except Exception:
                    return format_response(False, f"Line #{idx}: quantity must be a number", error_code=-111,
                                           http_status=400)
                if qty <= 0:
                    return format_response(False, f"Line #{idx}: quantity must be > 0", error_code=-112,
                                           http_status=400)

                product = Product.browse(int(pid))
                if not product.exists():
                    return format_response(False, f"Line #{idx}: product_id {pid} not found", error_code=-113,
                                           http_status=404)

                # ⟵ السعر من المنتج مباشرةً
                price_unit = product.lst_price

                # خصم اختياري (إن أُرسل) – أبقيناه كما هو
                discount = float(l.get('discount') or 0.0)
                if discount < 0 or discount > 100:
                    return format_response(False, f"Line #{idx}: discount must be between 0 and 100", error_code=-114,
                                           http_status=400)

                # الضرائب: إن لم تُرسل نأخذ الافتراضي من المنتج/الشركة
                tax_ids = l.get('tax_ids')
                if not tax_ids:
                    tax_ids = product.taxes_id.filtered(
                        lambda t: (not t.company_id) or (
                                    current_user.company_id and t.company_id.id == current_user.company_id.id)
                    ).ids

                invoice_line_cmds.append((0, 0, {
                    'name': product.display_name,
                    'product_id': product.id,
                    'quantity': qty,
                    'price_unit': price_unit,  # ← دائماً من المنتج
                    'discount': discount,
                    'tax_ids': [(6, 0, tax_ids)] if tax_ids else [(5, 0, 0)],
                }))

            move_vals = {
                'move_type': 'out_refund',
                'partner_id': partner.id,
                'invoice_date': fields.Date.context_today(current_user),
                'invoice_line_ids': invoice_line_cmds,
            }
            if currency_id:
                move_vals['currency_id'] = int(currency_id)
            else:
                if current_user.company_id and current_user.company_id.currency_id:
                    move_vals['currency_id'] = current_user.company_id.currency_id.id
            if journal_id:
                move_vals['journal_id'] = int(journal_id)
            if invoice_origin:
                move_vals['invoice_origin'] = invoice_origin
            if note:
                move_vals['ref'] = note
                move_vals['narration'] = note

            credit = AccountMove.create(move_vals)
            if credit.state == 'draft':
                credit.action_post()

            out_lines = []
            for ln in credit.invoice_line_ids:
                out_lines.append({
                    "line_id": ln.id,
                    "product_id": getattr(ln.product_id, 'id', None),
                    "product_name": noneify(getattr(ln.product_id, 'display_name', None)),
                    "quantity": ln.quantity,
                    "price_unit": ln.price_unit,
                    "discount": ln.discount,
                    "subtotal": ln.price_subtotal,

                    "total": ln.price_total,
                    "taxes": [t.name for t in ln.tax_ids] if ln.tax_ids else [],
                })

            response_data = {
                "credit_note_id": credit.id,
                "name": noneify(credit.name),
                "state": noneify(credit.state),
                "move_type": noneify(credit.move_type),
                "partner": noneify(credit.partner_id.display_name),
                "currency": noneify(credit.currency_id.name),
                "amount_untaxed": credit.amount_untaxed,
                "amount_tax": credit.amount_tax,
                "amount_total": credit.amount_total,
                "invoice_origin": noneify(credit.invoice_origin),
                "note": noneify(note),
                "lines": out_lines,
            }

            return format_response(True, "Credit note created & posted successfully.", response_data, http_status=200)

        except Exception as e:
            _logger.exception("Error while creating credit note (phase 2)")
            return format_response(False, f"Internal error: {str(e)}", error_code=-500, http_status=500)


    # ------------------------------------------------------------
    # Pay invoice / credit note using payment register wizard
    # ------------------------------------------------------------
    @http.route(
        '/sales_rep_manager/<string:api_version>/invoices/pay',
        type='http', auth='none', methods=['POST', 'OPTIONS'], csrf=False, cors='*'
    )
    @jwt_required()
    def pay_invoice_cash(self, **kwargs):
        if request.httprequest.method == 'OPTIONS':
            return json_response({"ok": True}, status=200)

        try:
            env = kwargs["_jwt_env"]
            current_user = env['res.users'].browse(kwargs["_jwt_user_id"])

            data, error = self._get_body()
            if error:
                return format_response(False, error, error_code=-100, http_status=400)

            # Required
            invoice_id = data.get('invoice_id') or data.get('move_id')
            if not invoice_id:
                return format_response(False, "Missing required parameter: invoice_id",
                                       error_code=-101, http_status=400)

            Move = env['account.move'].sudo()
            move = Move.browse(int(invoice_id))
            if not move.exists():
                return format_response(False, f"invoice_id {invoice_id} not found",
                                       error_code=-102, http_status=404)

            if move.move_type not in ('out_invoice', 'out_refund', 'in_invoice', 'in_refund'):
                return format_response(False, "Provided move is not an invoice/credit note.",
                                       error_code=-103, http_status=400)

            # Post if draft (safety)
            if move.state == 'draft':
                try:
                    move.action_post()
                except Exception as e:
                    return format_response(False, f"Cannot post the invoice before payment: {str(e)}",
                                           error_code=-104, http_status=400)

            # Optional inputs for payment
            amount = data.get('amount')  # float
            payment_date = data.get('payment_date') or data.get('date')
            # currency can be currency_id or currency_code
            currency_id = data.get('currency_id')
            currency_code = data.get('currency_code') or data.get('currency')

            # Journal resolution priority: explicit journal_id → (user+currency) cash journal → fallback 'cash'
            Journal = env['account.journal'].sudo()
            journal = None
            journal_id = data.get('journal_id')

            # Resolve currency if provided
            Currency = env['res.currency'].sudo()
            pay_currency = None
            if currency_id:
                pay_currency = Currency.browse(int(currency_id))
                if not pay_currency.exists():
                    return format_response(False, f"currency_id {currency_id} not found",
                                           error_code=-106, http_status=400)
            elif currency_code:
                pay_currency = Currency.search([('name', '=', currency_code)], limit=1)
                if not pay_currency:
                    pay_currency = Currency.search([('currency_unit_label', '=', currency_code)], limit=1)
                if not pay_currency:
                    return format_response(False, f"currency_code '{currency_code}' not found",
                                           error_code=-106, http_status=400)

            # 1) Use explicit journal if provided
            if journal_id:
                journal = Journal.browse(int(journal_id))
                if not journal.exists():
                    return format_response(False, f"journal_id {journal_id} not found",
                                           error_code=-105, http_status=400)
            else:
                # 2) Try resolve a cash journal mapped to (user, currency)
                #    يمكنك لاحقاً إنشاء إعداد واضح يربط user_id + currency_id بجورنال معيّن.
                #    هنا نحاول إيجاد جورنال نقدي بنفس عملة الدفع أو عملة الشركة إن لم تُرسل عملة.
                domain = [('type', '=', 'cash')]
                if current_user.company_id:
                    domain.append(('company_id', '=', current_user.company_id.id))
                candidate = Journal.search(domain, limit=50)

                def _match_currency(j):
                    if pay_currency:
                        # journal.currency_id قد يكون فارغ = يستخدم عملة الشركة
                        return (j.currency_id and j.currency_id.id == pay_currency.id) or \
                               (
                                           not j.currency_id and current_user.company_id and current_user.company_id.currency_id.id == pay_currency.id)
                    return True  # لا توجد عملة محددة

                # من بين المرشحين نقدّم ما يطابق العملة
                journal = next((j for j in candidate if _match_currency(j)), None)

                # 3) Fallback: أي جورنال اسمه cash
                if not journal:
                    journal = Journal.search([('name', 'ilike', 'cash')], limit=1)

                if not journal:
                    return format_response(False, "Cash journal not found. Please provide journal_id.",
                                           error_code=-105, http_status=400)

            # Build context for register wizard
            ctx = {
                'active_model': 'account.move',
                'active_ids': [move.id],
            }
            Register = env['account.payment.register'].with_context(ctx).sudo()

            vals = {
                'journal_id': journal.id,
            }
            if amount:
                vals['amount'] = float(amount)
            else:
                vals['amount'] = move.amount_residual  # default full residual

            if payment_date:
                vals['payment_date'] = payment_date

            # Create and execute payment
            reg = Register.create(vals)
            reg.action_create_payments()

            resp = {
                "invoice_id": move.id,
                "name": noneify(move.name),
                "move_type": noneify(move.move_type),
                "state": noneify(move.state),
                "payment_state": noneify(move.payment_state),
                "amount_total": move.amount_total,
                "amount_residual": move.amount_residual,
                "journal_used": {
                    "id": journal.id,
                    "name": noneify(journal.name),
                    "type": noneify(journal.type),
                    "currency": noneify(journal.currency_id.name or (
                        journal.company_id.currency_id.name if journal.company_id else None)),
                }
            }
            return format_response(True, "Payment registered successfully.", resp, http_status=200)

        except Exception as e:
            _logger.exception("Error while registering payment")
            return format_response(False, f"Internal error: {str(e)}", error_code=-500, http_status=500)
