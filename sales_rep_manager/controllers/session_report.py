# controllers/session_management.py
# -*- coding: utf-8 -*-

import logging
from datetime import datetime

from odoo import http
from odoo.http import request
from .api_utils import json_response, jwt_required, format_response, noneify

_logger = logging.getLogger(__name__)


class SessionReportAPI(http.Controller):
    """Endpoints لتقرير الجلسة حسب المندوب والفترة (stateless JWT)."""

    # ------------------------ Helpers ------------------------

    def _preflight(self):
        if request.httprequest.method == "OPTIONS":
            return json_response({"ok": True}, status=200)
        return None

    def _get_body(self):
        try:
            data = request.get_json_data() or {}
            if not isinstance(data, dict):
                return None, "Invalid JSON: body must be an object"
            return data, None
        except Exception:
            return {}, None

    @staticmethod
    def _parse_date(val, end=False):
        if not val:
            return None
        try:
            dt = datetime.strptime(val, "%Y-%m-%d")
            return dt.replace(hour=23, minute=59, second=59) if end else dt.replace(hour=0, minute=0, second=0)
        except Exception:
            return None

    def _model(self, env, name, company_id=None):
        m = env[name]
        if company_id:
            try:
                m = m.with_company(int(company_id))
            except Exception:
                pass
        return m.sudo()

    def _read_inputs(self):
        body, _ = self._get_body()
        params = request.params or {}

        date_from_raw = params.get("date_from") or (body or {}).get("date_from")
        date_to_raw = params.get("date_to") or (body or {}).get("date_to")
        company_id = params.get("company_id") or (body or {}).get("company_id")

        date_from = self._parse_date(date_from_raw, end=False)
        date_to = self._parse_date(date_to_raw, end=True)

        return date_from, date_to, company_id

    # ------------------------ Qty Helpers ------------------------

    @staticmethod
    def _infer_qty_from_invoice_line(line):
        q = float(line.quantity or 0.0)
        if q:
            return abs(q)
        pu = float(line.price_unit or 0.0)
        if not pu:
            return 0.0
        ps = float(getattr(line, "price_subtotal", 0.0) or 0.0)
        return abs(ps / pu) if ps else 0.0

    @staticmethod
    def _infer_qty_from_journal_line(line):
        q = float(line.quantity or 0.0)
        if q:
            return abs(q)
        pu = float(getattr(line, "price_unit", 0.0) or 0.0)
        if not pu:
            return 0.0
        bal = float(line.balance or 0.0)
        return abs(bal / pu) if bal else 0.0

    @classmethod
    def _sum_qty_from_invoice_lines(cls, moves):
        qty = 0.0
        for mv in moves:
            lines = mv.invoice_line_ids
            for l in lines:
                qty += cls._infer_qty_from_invoice_line(l)
        return qty

    @classmethod
    def _sum_qty_from_product_journal_lines(cls, moves):
        qty = 0.0
        for mv in moves:
            lines = mv.line_ids.filtered(lambda l: (not l.display_type) and bool(l.product_id))
            for l in lines:
                qty += cls._infer_qty_from_journal_line(l)
        return qty

    @staticmethod
    def _sum_qty_from_sale_links(moves):
        qty = 0.0
        for mv in moves:
            inv_lines = mv.invoice_line_ids.filtered(lambda l: not l.display_type)
            for l in inv_lines:
                if l.sale_line_ids:
                    qty += sum(float(sl.product_uom_qty or 0.0) for sl in l.sale_line_ids)
            j_lines = mv.line_ids.filtered(lambda l: (not l.display_type) and bool(l.product_id))
            for l in j_lines:
                if l.sale_line_ids:
                    qty += sum(float(sl.product_uom_qty or 0.0) for sl in l.sale_line_ids)
        return qty

    @staticmethod
    def _extract_sale_names_from_origin(origin):
        if not origin:
            return []
        return [p.strip() for p in str(origin).split(",") if p and str(p).strip()]

    def _sum_qty_from_invoice_origin_sales(self, env, moves, company_id=None):
        SaleOrder = self._model(env, "sale.order", company_id)
        all_names = []
        for mv in moves:
            all_names += self._extract_sale_names_from_origin(mv.invoice_origin)
        for mv in moves:
            rev = getattr(mv, "reversed_entry_id", None)
            if rev:
                all_names += self._extract_sale_names_from_origin(rev.invoice_origin)
        all_names = list(dict.fromkeys([n for n in all_names if n]))
        if not all_names:
            return 0.0
        orders = SaleOrder.search([("name", "in", all_names)])
        return sum(float(l.product_uom_qty or 0.0) for so in orders for l in so.order_line)

    def _sum_move_qty_robust(self, env, moves, company_id=None):
        q1 = self._sum_qty_from_invoice_lines(moves)
        if q1: return q1
        q2 = self._sum_qty_from_product_journal_lines(moves)
        if q2: return q2
        q3 = self._sum_qty_from_sale_links(moves)
        if q3: return q3
        q4 = self._sum_qty_from_invoice_origin_sales(env, moves, company_id=company_id)
        return q4

    @staticmethod
    def _sum_amounts_by_currency_signed(moves):
        out = {}
        for mv in moves:
            cur = mv.currency_id
            cur_name = (cur and (cur.name or "") or "").upper() or ""
            out[cur_name] = out.get(cur_name, 0.0) + float(mv.amount_total_signed or 0.0)
        return out

    # ------------------------ Payment Helper (Updated for SPO) ------------------------

    # ------------------------ Payment Helper (Updated for SPO) ------------------------

    # ------------------------ Payment Helper (Updated for SPO) ------------------------

    def _get_payments_sum(self, env, user_id, date_from, date_to, company_id, payment_type):
        """
        يرجع (total_syp, total_usd, total_old_syp)
        حيث يتم تمييز القديم برمز العملة "SPO"
        """
        AccountPayment = self._model(env, "account.payment", company_id)

        # 1. الدومين: يبحث عن كل الدفعات لهذا المستخدم في هذه الفترة
        domain = [
            ("payment_type", "=", payment_type),
            ("state", "in", ["in_process", "paid"]),
            ("create_uid", "=", user_id),
        ]

        if company_id:
            domain.append(("company_id", "=", int(company_id)))

        if date_from:
            domain.append(("date", ">=", date_from.date()))
        if date_to:
            domain.append(("date", "<=", date_to.date()))

        # 2. جلب البيانات
        payments = AccountPayment.search(domain)

        # --- (تم الحذف) ---
        # قمنا بحذف السطر التالي لكي تظهر الدفعات المستقلة (غير المربوطة بفواتير)
        # payments = payments.filtered(lambda p: p.reconciled_invoice_ids)
        # ------------------

        _logger.info(
            "SESSION REPORT .................| user_id=%s | payment_type=%s | payments_count=%s",
            user_id,
            payment_type,
            len(payments),
        )

        total_syp = 0.0
        total_usd = 0.0
        total_old_syp = 0.0  # SPO

        for pay in payments:
            cur = pay.currency_id
            cur_name = (cur and (cur.name or "") or "").upper()
            cur_symbol = (cur and (getattr(cur, "symbol", "") or "") or "")

            amt = float(pay.amount or 0.0)

            # 1. فحص SPO (الليرة القديمة)
            if cur_name == "SPO":
                total_old_syp += amt

            # 2. فحص الدولار
            elif (cur_name == "USD") or ("$" in cur_symbol):
                total_usd += amt

            # 3. الباقي يعتبر ليرة سورية عادية (SYP / SYR)
            elif cur_name in ("SYP", "SYR", "SP", "S.P") or ("ل.س" in cur_symbol):
                total_syp += amt

        return total_syp, total_usd, total_old_syp
        # ------------------------ Core ------------------------

    def _build_session_payload(self, env, user_id, date_from, date_to, company_id=None):
        # 1) الطلبات
        so_domain = [("user_id", "=", user_id)]
        if date_from: so_domain.append(("date_order", ">=", date_from))
        if date_to: so_domain.append(("date_order", "<=", date_to))

        SaleOrder = self._model(env, "sale.order", company_id)
        sale_orders = SaleOrder.search(so_domain)
        orders_count = len(sale_orders)

        incomplete_orders_count = len(sale_orders.filtered(lambda so: so.state in ("draft", "sent")))
        confirmed_orders = sale_orders.filtered(lambda so: so.state in ("sale", "done"))
        items_sold_count = sum(float(line.product_uom_qty or 0.0) for so in confirmed_orders for line in so.order_line)

        # 2) الفواتير
        inv_domain = [
            ("move_type", "=", "out_invoice"),
            ("state", "=", "posted"),
            ("invoice_user_id", "=", user_id),
        ]
        if date_from: inv_domain.append(("date", ">=", date_from.date()))
        if date_to: inv_domain.append(("date", "<=", date_to.date()))

        AccountMove = self._model(env, "account.move", company_id)
        invoices = AccountMove.search(inv_domain)
        invoices_count = len(invoices)
        invoice_lines_qty = self._sum_move_qty_robust(env, invoices, company_id=company_id)

        # فصل إجمالي الفواتير حسب العملة (SPO, USD, SYP)
        inv_syp_total = 0.0
        inv_usd_total = 0.0
        inv_old_syp_total = 0.0

        for mv in invoices:
            cur = mv.currency_id
            cur_name = (cur and (cur.name or "") or "").upper()
            cur_symbol = (cur and (getattr(cur, "symbol", "") or "") or "")
            amt = float(mv.amount_total or 0.0)

            if cur_name == "SPO":
                inv_old_syp_total += amt
            elif (cur_name == "USD") or ("$" in cur_symbol):
                inv_usd_total += amt
            elif cur_name in ("SYP", "SYR", "SP", "S.P") or ("ل.س" in cur_symbol):
                inv_syp_total += amt

        # 3) المرتجعات
        refund_domain = [
            ("move_type", "=", "out_refund"),
            ("state", "=", "posted"),
            ("invoice_user_id", "=", user_id),
        ]
        if date_from: refund_domain.append(("date", ">=", date_from.date()))
        if date_to: refund_domain.append(("date", "<=", date_to.date()))

        refunds = AccountMove.search(refund_domain)
        returns_count = len(refunds)
        returned_qty = self._sum_move_qty_robust(env, refunds, company_id=company_id)

        ref_syp_total = 0.0
        ref_old_syp_total = 0.0

        for mv in refunds:
            cur = mv.currency_id
            cur_name = (cur and (cur.name or "") or "").upper()
            cur_symbol = (cur and (getattr(cur, "symbol", "") or "") or "")
            amt = float(mv.amount_total or 0.0)

            if cur_name == "SPO":
                ref_old_syp_total += amt
            elif cur_name in ("SYP", "SYR", "SP", "S.P") or ("ل.س" in cur_symbol):
                ref_syp_total += amt

        # 4) الدفعات (Payments) - استدعاء الدالة
        receipts_syp, receipts_usd, receipts_old_syp = self._get_payments_sum(
            env, user_id, date_from, date_to, company_id, payment_type="inbound"
        )

        disbursements_syp, disbursements_usd, disbursements_old_syp = self._get_payments_sum(
            env, user_id, date_from, date_to, company_id, payment_type="outbound"
        )

        # 5) الصافي (Net Cash)
        net_cash_syp = receipts_syp - disbursements_syp
        net_cash_usd = receipts_usd - disbursements_usd
        net_cash_old_syp = receipts_old_syp - disbursements_old_syp  # صافي SPO

        # 6) تجهيز التقرير
        totals_by_currency = {}
        for inv in invoices:
            cur = inv.currency_id
            cur_name = (cur and (cur.name or "") or "").upper()
            amt = float(inv.amount_total or 0.0)
            totals_by_currency[cur_name or ""] = totals_by_currency.get(cur_name or "", 0.0) + amt

        totals_by_currency_list = [{"currency": noneify(k), "amount_total": v} for k, v in totals_by_currency.items()]

        net_inv = self._sum_amounts_by_currency_signed(invoices)
        net_ref = self._sum_amounts_by_currency_signed(refunds)
        for k, v in net_ref.items():
            net_inv[k] = net_inv.get(k, 0.0) + v
        totals_by_currency_with_refunds = [{"currency": noneify(k), "amount_total": v} for k, v in net_inv.items()]

        user = env["res.users"].browse(user_id)

        arabic_block = {
            "يمين": {
                "عدد الطلبيات": orders_count,
                "عدد الفواتير": invoices_count,
                "عدد القطع المباعة": invoice_lines_qty,
                "إجمالي الفواتير ل.س": inv_syp_total,
                "إجمالي المقبوضات ل.س": receipts_syp,
                "إجمالي المقبوضات ل.س قديمة": receipts_old_syp,  # SPO Inbound
                "إجمالي المقبوضات $": receipts_usd,
            },
            "يسار": {
                "عدد المرتجعات": returns_count,
                "عدد القطع المعادة": returned_qty,
                "إجمالي فواتير المرتجعات ل.س": ref_syp_total,
                "إجمالي المدفوعات ل.س": disbursements_syp,
                "إجمالي المدفوعات ل.س قديمة": disbursements_old_syp,  # SPO Outbound
                "إجمالي المدفوعات $": disbursements_usd,
            },
            "سفلي": {
                "الصافي ل.س": net_cash_syp,
                "الصافي ل.س قديمة": net_cash_old_syp,  # SPO Net
                "الصافي $": net_cash_usd,
            },
        }

        documents_count = invoices_count + returns_count
        lines_qty_total = invoice_lines_qty - returned_qty

        return {
            "user": {"id": user.id, "name": noneify(user.name)},
            "period": {
                "date_from": date_from.strftime("%Y-%m-%d") if date_from else None,
                "date_to": date_to.strftime("%Y-%m-%d") if date_to else None,
            },
            "orders_count": orders_count,
            "invoices_count": invoices_count,
            "invoice_lines_qty": invoice_lines_qty,
            "totals_by_currency": totals_by_currency_list,
            "returns_count": returns_count,
            "returned_qty": returned_qty,
            "documents_count": documents_count,
            "lines_qty_total": lines_qty_total,
            "totals_by_currency_with_refunds": totals_by_currency_with_refunds,
            "items_sold_count": items_sold_count,
            "incomplete_orders_count": incomplete_orders_count,
            "عربي": arabic_block,
        }

    # ------------------------ Endpoint ------------------------

    @http.route(
        "/sales_rep_manager/<string:api_version>/session/report",
        type="http",
        auth="none",
        methods=["GET", "POST", "OPTIONS"],
        csrf=False,
        cors="*",
    )
    @jwt_required()
    def session_report(self, api_version=None, **kwargs):
        pre = self._preflight()
        if pre:
            return pre

        try:
            env = kwargs["_jwt_env"]
            user_id = int(kwargs["_jwt_user_id"])

            date_from, date_to, company_id = self._read_inputs()

            payload = self._build_session_payload(env, user_id, date_from, date_to, company_id)
            return format_response(True, "Session report fetched successfully", payload, http_status=200)

        except Exception as e:
            _logger.exception("Error building session report")
            return format_response(False, f"Internal error: {str(e)}", error_code=-500, http_status=500)