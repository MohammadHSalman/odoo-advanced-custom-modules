# -*- coding: utf-8 -*-
# Done+++++++++++++++++++++++++++++++

import json
import logging
import time
from datetime import datetime, timedelta

import jwt
from odoo import http
from odoo.http import request
from odoo.modules.registry import Registry
from odoo import api

_logger = logging.getLogger(__name__)

# ---- CORS & JSON helpers ---------------------------------------------------------
def _cors_headers():
    return [
        ('Content-Type', 'application/json; charset=utf-8'),
        ('Access-Control-Allow-Origin', '*'),
        ('Access-Control-Allow-Methods', 'GET, POST, OPTIONS'),
        ('Access-Control-Allow-Headers', 'Content-Type, Authorization, X-DB'),
    ]

def json_response(payload, status=200):
    body = json.dumps(payload, ensure_ascii=False, default=str)
    return http.Response(body, status=status, headers=_cors_headers())

# (توافق) دوالك السابقة التي يستعملها باقي الكنترولرز
def get_json_data():
    """Safely parse request JSON body. Returns (data, error_str)."""
    raw = request.httprequest.data
    if not raw:
        return None, "Request body is empty."
    try:
        return json.loads(raw), None
    except json.JSONDecodeError:
        return None, "Invalid JSON format in request body."
    except Exception as e:
        _logger.error(f"Error parsing JSON data: {e}")
        return None, "An unexpected error occurred while reading the request body."

def format_response(success, message, data=None, error_code=None, status_code=None):
    """
    Unified REST response on top of json_response (adds CORS).
    - success=True  => default HTTP 200
    - success=False => default HTTP 400
    """
    if not success and error_code is not None and error_code > 0:
        error_code = -error_code
    if not success and error_code is None:
        error_code = -100

    payload = {
        "statuscode": 0 if success else error_code,
        "message": message,
        "data": data if data is not None else {}
    }
    http_status = status_code if status_code is not None else (200 if success else 400)
    _logger.info("API Response: %s (HTTP %s)", payload, http_status)
    return json_response(payload, status=http_status)

# ---- Config from ir.config_parameter ---------------------------------------------
def _get_param(key, default=None):
    try:
        return request.env['ir.config_parameter'].sudo().get_param(key, default)
    except Exception:
        return default

def get_jwt_secret():
    return _get_param("auth_jwt_api.secret", "CHANGE_ME_SECRET")

def get_jwt_algorithm():
    return _get_param("auth_jwt_api.algorithm", "HS256")

def get_access_ttl_seconds():
    v = _get_param("auth_jwt_api.access_ttl_seconds", "86400")
    try:
        return int(v)
    except Exception:
        return 86400

def get_refresh_ttl_seconds():
    v = _get_param("auth_jwt_api.refresh_ttl_seconds", "1209600")  # 14 days
    try:
        return int(v)
    except Exception:
        return 1209600

# ---- DB resolve (multi-db support) ----------------------------------------------
def resolve_dbname(require=True):
    """
    Priority: ?db=, then header X-DB, then Odoo config single db.
    """
    db = request.params.get("db") or request.httprequest.headers.get("X-DB")
    if not db:
        # Fallback to Odoo-configured single db if present
        try:
            from odoo.tools import config as odoo_config
            single = odoo_config.get('db_name')
            if single:
                db = single
        except Exception:
            pass

    if not db:
        if require:
            raise ValueError("Missing database name. Pass ?db= or X-DB header, or set db_name in the config.")
        return None

    # Basic sanity check (allow letters, digits, underscore, hyphen)
    import re
    if not re.match(r'^[A-Za-z0-9\-_]+$', db):
        raise ValueError("Invalid DB name. Use letters, digits, underscore, or hyphen.")

    return db

# ---- JWT encode/decode -----------------------------------------------------------
def make_access_token(user_id, login, dbname):
    now = int(time.time())
    payload = {
        "sub": str(user_id),           # RFC7519: subject should be string
        "login": login,
        "db": dbname,
        "type": "access",
        "iat": now,
        # "exp": now + get_access_ttl_seconds(),
    }
    return jwt.encode(payload, get_jwt_secret(), algorithm=get_jwt_algorithm())

def make_refresh_token(user_id, login, dbname):
    now = int(time.time())
    payload = {
        "sub": str(user_id),           # RFC7519: subject should be string
        "login": login,
        "db": dbname,
        "type": "refresh",
        "iat": now,
        "exp": now + get_refresh_ttl_seconds(),
    }
    return jwt.encode(payload, get_jwt_secret(), algorithm=get_jwt_algorithm())

def decode_token(token, expected_type=None):
    try:
        data = jwt.decode(
            token,
            get_jwt_secret(),
            algorithms=[get_jwt_algorithm()],
            options={"verify_sub": False}  # تخفيف مؤقت لقبول توكنات قديمة إن وجدت
        )
        if expected_type and data.get("type") != expected_type:
            raise jwt.InvalidTokenError("Wrong token type")
        return data
    except jwt.ExpiredSignatureError:
        raise http.AccessDenied("Token expired")
    except Exception as e:
        raise http.AccessDenied(f"Invalid token: {e}")

# ---- Decorator: require JWT (stateless) ------------------------------------------
def jwt_required(expected_type="access"):
    """
    Usage:
      @jwt_required()          -> require access token
      @jwt_required('refresh') -> require refresh token
    """
    def _decorator(func):
        def _wrapped(*args, **kwargs):
            # CORS preflight
            if request.httprequest.method == "OPTIONS":
                return json_response({"ok": True, "message": "CORS preflight"}, 200)

            # Extract Bearer
            auth_header = request.httprequest.headers.get("Authorization", "")
            if not auth_header.startswith("Bearer "):
                return json_response({"statuscode": 401, "message": "Missing Bearer token"}, 401)
            token = auth_header.split(" ", 1)[1].strip()

            try:
                data = decode_token(token, expected_type=expected_type)
                db_in_token = data.get("db")
                user_id = int(data.get("sub") or 0)
                if not db_in_token or not user_id:
                    return json_response({"statuscode": 401, "message": "Invalid token payload"}, 401)

                # افتح ريجستري وكرسر، وابنِ Environment
                registry = Registry(db_in_token)
                with registry.cursor() as cr:
                    env = api.Environment(cr, user_id, {})

                    # ✅ اجعل الـ env متاحاً لكل من kwargs و request.env
                    kwargs["_jwt_env"] = env
                    kwargs["_jwt_user_id"] = user_id
                    kwargs["_jwt_login"] = data.get("login")
                    kwargs["_jwt_db"] = db_in_token

                    # هذه الخطوة هي التي تحل الخطأ:
                    request.env = env  # لا تنشئ جلسة؛ فقط توفّر env لمن يعتمد عليه ضمنيًا
                    # لو تحب أيضاً:
                    # request.cr = cr  # عادة Odoo يضبطها، لكن لا ضرر من ضمانها

                    res = func(*args, **kwargs)
                    cr.commit()
                    return res

            except http.AccessDenied as e:
                return json_response({"statuscode": 401, "message": str(e)}, 401)
            except Exception as e:
                _logger.exception("JWT route error")
                return json_response({"statuscode": 500, "message": str(e)}, 500)

        return _wrapped
    return _decorator
def noneify(v):
    """حوّل False/None/'' إلى None، واترك الباقي كما هو (لا يمس 0 أو True/False المنطقيين)."""
    if v is False or v is None:
        return None
    if isinstance(v, str) and v.strip() == "":
        return None
    return v
def format_response(success, message, data=None, error_code=None, http_status=200):
    payload = {
        "statuscode": http_status,
        "success": bool(success),
        "message": message,
    }
    if data is not None:
        payload["data"] = data
    if error_code is not None:
        payload["error_code"] = error_code
    return json_response(payload, status=http_status)