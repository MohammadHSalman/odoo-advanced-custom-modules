# -*- coding: utf-8 -*-
import json
import logging
from datetime import datetime

from odoo import http
from odoo.http import request

from .api_utils import json_response, jwt_required, format_response

_logger = logging.getLogger(__name__)


class LocationTrackingAPI(http.Controller):

    @http.route(
        '/sales_rep_manager/<string:api_version>/location',
        type='http',
        auth='none',
        methods=['POST', 'OPTIONS'],
        csrf=False,
        cors='*'
    )
    @jwt_required()
    def receive_location(self, **kwargs):
        if request.httprequest.method == 'OPTIONS':
            return json_response({"ok": True}, status=200)

        env = kwargs['_jwt_env']
        current_user = env['res.users'].browse(kwargs['_jwt_user_id'])

        try:
            raw = request.httprequest.get_data(as_text=True)
            if not raw:
                return format_response(False, "البيانات فارغة", http_status=400)

            body = json.loads(raw)

            rep_profile = env['sales.rep.profile'].sudo().search(
                [('user_id', '=', current_user.id)], limit=1
            )

            if not rep_profile:
                return format_response(False, "لا يوجد ملف مندوب لهذا المستخدم", http_status=404)

            lat = body.get('latitude') or body.get('lat')
            lng = body.get('longitude') or body.get('lng')
            ts = body.get('timestamp') or body.get('location_time')

            if lat is None or lng is None or ts is None:
                return format_response(False, "البيانات المطلوبة ناقصة", http_status=400)

            location_time = self._parse_timestamp(ts)
            if not location_time:
                return format_response(False, "صيغة الوقت غير صحيحة", http_status=400)

            new_location = env['sales.rep.location'].sudo().create({
                'sales_rep_id': rep_profile.id,
                'latitude': float(lat),
                'longitude': float(lng),
                'location_time': location_time,
            })

            return format_response(True, "تم حفظ الموقع", http_status=200)

        except json.JSONDecodeError:
            return format_response(False, "JSON غير صالح", http_status=400)
        except Exception:
            return format_response(False, "خطأ داخلي في الخادم", http_status=500)

    def _parse_timestamp(self, ts):
        """Convert any timestamp format to datetime"""
        if not ts:
            return None
        try:
            if isinstance(ts, (int, float)):
                if ts > 1e10:
                    ts = ts / 1000
                return datetime.utcfromtimestamp(ts)

            if isinstance(ts, str):
                for fmt in ('%Y-%m-%dT%H:%M:%S',
                            '%Y-%m-%dT%H:%M:%SZ',
                            '%Y-%m-%dT%H:%M:%S.%fZ',
                            '%Y-%m-%d %H:%M:%S'):
                    try:
                        return datetime.strptime(ts, fmt)
                    except:
                        continue
        except:
            pass

        return None
