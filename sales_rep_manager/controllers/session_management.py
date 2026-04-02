# -*- coding: utf-8 -*-
import logging
from odoo import http, SUPERUSER_ID
from odoo.http import request
from odoo.modules.registry import Registry
from odoo import api
from odoo.exceptions import AccessDenied
from .api_utils import make_access_token

_logger = logging.getLogger(__name__)


class SessionManagement(http.Controller):
    DATABASE_NAME = "nad_mobile"

    @http.route('/sales_rep_manager/<string:api_version>/login', type='json', auth='none',
                methods=['POST', 'OPTIONS'], csrf=False, cors="*")
    def login(self, api_version, **kwargs):
        if request.httprequest.method == 'OPTIONS':
            return {"ok": True}

        params = request.get_json_data() or {}
        login = params.get('login') or params.get('email')
        password = params.get('password')

        if not login or not password:
            return {"statuscode": 400, "message": "Missing 'login' or 'password' in JSON body."}

        dbname = self.DATABASE_NAME

        try:
            # ? ????? Odoo 18 ???????
            credential = {
                'login': login,
                'password': password,
                'type': 'password'
            }
            request.session.authenticate(dbname, credential)

            # ?????? ?? ???? ????? ??????
            uid = request.session.uid

            if not uid:
                return {"statuscode": 401, "message": "Invalid credentials"}

            registry = Registry(dbname)
            with registry.cursor() as cr:
                env = api.Environment(cr, SUPERUSER_ID, {})
                user = env['res.users'].sudo().browse(uid)

                profile = env['sales.rep.profile'].sudo().search([('user_id', '=', user.id)], limit=1)
                sales_team_type = profile.sales_team_type if profile else None
                access = make_access_token(user.id, user.login, dbname)
                cr.commit()

                # ??? ?????? ????? ?????? ???? (stateless)
                request.session.logout(keep_db=True)

                AccountMove = env['account.move'].sudo()

                invoices = AccountMove.search([
                    ('user_id', '=', user.id),
                    ('mobile_invoice_number', '!=', False),
                    ('move_type', '=', 'out_invoice')
                ])

                # نختار الفاتورة مع أكبر رقم في النهاية
                last_inv = max(
                    invoices,
                    key=lambda inv: int(inv.mobile_invoice_number.split('-')[-1])
                ) if invoices else None

                last_local_invoice = last_inv.mobile_invoice_number if last_inv else None

                # 2. جلب آخر فاتورة مرتجع
                last_return = AccountMove.search([
                    ('user_id', '=', user.id),
                    ('mobile_invoice_number', '!=', False),
                    ('move_type', '=', 'out_refund')
                ])

                # نختار الفاتورة مع أكبر رقم في النهاية
                last_inv_return = max(
                    last_return,
                    key=lambda inv: int(inv.mobile_invoice_number.split('-')[-1])
                ) if last_return else None

                last_local_return_invoice = last_inv_return.mobile_invoice_number if last_inv_return else None

                # 3. (الجديد) جلب إعدادات التقريب الخاصة بـ NAD Cash Rounding
                rounding_val = 0.0
                rounding_rec = env['account.cash.rounding'].sudo().search([
                    ('name', '=', 'NAD Cash Rounding')
                ], limit=1)

                if rounding_rec:
                    rounding_val = rounding_rec.rounding

                return {
                    "statuscode": 200,
                    "message": "Login successful",
                    "access_token": access,
                    "token_type": "Bearer",
                    "expires_in": None,
                    "user": {
                        "id": user.id,
                        "login": user.login,
                        "name": user.name,
                        "sales_team_type": sales_team_type
                    },
                    "sequence": profile.sequence if (profile and profile.sequence) else None,
                    "attachment_mandatory": profile.attachment_mandatory,
                    "allowed_distance_m": profile.allowed_distance_m,
                    "last_local_invoice": last_local_invoice,
                    "last_local_return_invoice": last_local_return_invoice,
                    "nad_rounding_value": rounding_val,  # القيمة الجديدة
                    "db": dbname,
                }

        except AccessDenied:
            return {"statuscode": 401, "message": "Invalid credentials"}
        except Exception as e:
            _logger.exception("Authentication error")
            return {"statuscode": 500, "message": str(e)}
    @http.route('/sales_rep_manager/<string:api_version>/logout', type='json', auth='none',
                methods=['POST', 'OPTIONS'], csrf=False, cors="*")
    def logout(self, api_version, **kwargs):
        if request.httprequest.method == 'OPTIONS':
            return {"ok": True}
        return {
            "statuscode": 200,
            "message": "Logged out (stateless). Please discard the token on the client.",
        }

    @http.route('/sales_rep_manager/<string:api_version>/forgot_password', type='json', auth='none',
                methods=['POST', 'OPTIONS'], csrf=False, cors="*")
    def forgot_password(self, api_version, **kwargs):
        if request.httprequest.method == 'OPTIONS':
            return {"ok": True}

        params = request.get_json_data() or {}
        email = params.get('email')
        if not email:
            return {"statuscode": 400, "message": "Email is required."}

        dbname = self.DATABASE_NAME
        try:
            registry = Registry(dbname)
            with registry.cursor() as cr:
                env = api.Environment(cr, SUPERUSER_ID, {})
                user = env['res.users'].sudo().search([('login', '=', email)], limit=1)
                if not user:
                    return {"statuscode": 404, "message": "No user found with this email."}

                user.sudo().action_reset_password()
                code = getattr(user, "password_reset_code", "") or ""
                cr.commit()
                return {
                    "statuscode": 200,
                    "message": "Password reset instructions have been sent to your email",
                    "data": {"verification_code": code},
                }
        except Exception as e:
            _logger.exception("Forgot password error")
            return {"statuscode": 500, "message": str(e)}

    @http.route('/sales_rep_manager/<string:api_version>/reset_password', type='json', auth='none',
                methods=['POST', 'OPTIONS'], csrf=False, cors="*")
    def reset_password(self, api_version, **kwargs):
        if request.httprequest.method == 'OPTIONS':
            return {"ok": True}

        params = request.get_json_data() or {}
        email = params.get('email')
        new_password = params.get('new_password')
        confirm_password = params.get('confirm_password')

        if not email or not new_password or not confirm_password:
            return {"statuscode": 400, "message": "Missing required parameters"}

        if new_password != confirm_password:
            return {"statuscode": 400, "message": "Passwords do not match"}

        dbname = self.DATABASE_NAME
        try:
            registry = Registry(dbname)
            with registry.cursor() as cr:
                env = api.Environment(cr, SUPERUSER_ID, {})
                user = env['res.users'].sudo().search([('login', '=', email)], limit=1)
                if not user:
                    return {"statuscode": 404, "message": "User not found"}

                user.sudo().write({'password': new_password})
                cr.commit()
                return {"statuscode": 200, "message": "Password has been reset successfully"}
        except Exception as e:
            _logger.exception("Reset password error")
            return {"statuscode": 500, "message": str(e)}
