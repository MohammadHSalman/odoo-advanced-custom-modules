# -*- coding: utf-8 -*-
# Done+++++++++++++++++++++++++++++++
from collections import defaultdict

import logging
import json
from datetime import datetime,time

from odoo import http, fields
from odoo.http import request
from .api_utils import json_response, jwt_required, noneify, format_response

_logger = logging.getLogger(__name__)


# ============================================================================
# Helpers
# ============================================================================

def _parse_image_sizes(arg):
    """
    يحوّل قيمة مثل "128,256,512" إلى قائمة أعداد [128, 256, 512].
    يعيد القيمة الافتراضية [128, 256, 512, 1024] إذا لم تُمرر قيمة صالحة.
    """
    if not arg:
        return [128, 256, 512, 1024]
    out = []
    for p in str(arg).split(','):
        p = p.strip()
        if p.isdigit():
            out.append(int(p))
    return out or [128, 256, 512, 1024]


def safe(value):
    return value or None


def _image_url(model, rec_id, field):
    """يبني رابط /web/image مع حفظ اسم المضيف الحالي."""
    base = request.httprequest.host_url.rstrip('/')
    return f"{base}/web/image/{model}/{rec_id}/{field}"


def _image_url_resized(model, rec_id, field='image_1920', size=None):
    """
    يبني رابط /web/image مع خيار تغيير المقاس عبر resize=WxH
    يعمل حتى لو ما كانت الحقول image_256/512 موجودة.
    """
    base = request.httprequest.host_url.rstrip('/')
    url = f"{base}/web/image?model={model}&id={rec_id}&field={field}"
    if size:
        url += f"&resize={size}x{size}"
    return url


def _product_image_urls(prod, sizes, prefer_variant=True):
    """
    يرجّع dict لروابط الصور بالمقاسات المطلوبة.
    يختار المصدر الذي يحتوي فعليًا صورة: الفاريانت ثم التيمبلِت.
    """
    prod_full = prod.with_context(bin_size=False)
    tmpl_full = prod.product_tmpl_id.with_context(bin_size=False) if prod.product_tmpl_id else None

    has_prod_img = bool(getattr(prod_full, 'image_1920', False) or getattr(prod_full, 'image_128', False))
    has_tmpl_img = bool(
        tmpl_full and (getattr(tmpl_full, 'image_1920', False) or getattr(tmpl_full, 'image_128', False)))

    model = None
    rec_id = None
    if prefer_variant and has_prod_img:
        model, rec_id = "product.product", prod.id
    elif has_tmpl_img:
        model, rec_id = "product.template", prod.product_tmpl_id.id
    else:
        # لا توجد صورة فعلية؛ نعيد روابط placeholder من التيمبلِت (لن تكسر الواجهة)
        model, rec_id = "product.template", (prod.product_tmpl_id.id if prod.product_tmpl_id else prod.id)

    urls = {}
    for s in sizes:
        urls[str(s)] = _image_url_resized(model, rec_id, 'image_1920', size=int(s))
    return urls


def _parse_bool(val, default=False):
    """تحويل قيمة نصية إلى Boolean."""
    if val is None:
        return default
    return str(val).lower() in ('1', 'true', 'yes', 'y')


def _parse_date(val):
    """
    يقبل YYYY-MM-DD أو YYYY-MM-DD HH:MM:SS
    ويعيد datetime أو None.
    """
    if not val:
        return None
    for fmt in ('%Y-%m-%d', '%Y-%m-%d %H:%M:%S'):
        try:
            return datetime.strptime(val, fmt)
        except Exception:
            continue
    return None


def _get_user_route_customers(env, current_user):
    """
    يرجّع جميع الزبائن المربوطين بمسارات المندوب (sales.rep.profile.route_id.partner_ids)
    بغض النظر عن partner.user_id.
    """
    PartnerModel = env['res.partner'].sudo()
    customers = PartnerModel.browse()
    print(customers, '---------------------')

    rep_profiles = env['sales.rep.profile'].sudo().search([
        ('user_id', '=', current_user.id)
    ])
    print(rep_profiles, '+++++++++++++++++++++++++')

    if not rep_profiles:
        return customers  # فارغ => لا يوجد أي عميل مسموح

    for profile in rep_profiles:
        if profile.route_id and profile.route_id.partner_ids:
            customers |= profile.route_id.partner_ids

    # إزالة التكرار إن وجد
    return customers


# ============================================================================
# Controller (Stateless JWT)
# ============================================================================

class GetData(http.Controller):

    @http.route([
        '/sales_rep_manager/<string:api_version>/get_products',
        '/sales_rep_manager/<string:api_version>/products',  # alias
    ], type='http', auth='none', methods=['GET', 'OPTIONS'], csrf=False, cors="*")
    @jwt_required()
    def get_products(self, **kwargs):
        # CORS preflight
        if request.httprequest.method == 'OPTIONS':
            return json_response({"ok": True}, status=200)

        try:
            env = kwargs["_jwt_env"]
            current_user = env['res.users'].browse(kwargs["_jwt_user_id"])

            # ---------- بروفايل المندوب ----------
            rep_profile = env['sales.rep.profile'].sudo().search([
                ('user_id', '=', current_user.id)
            ], limit=1)
            if not rep_profile or not rep_profile.location_id:
                return format_response(
                    False,
                    "No location assigned to this sales representative",
                    error_code=-404,
                    http_status=200
                )

            location_id = rep_profile.location_id.id
            user_name = current_user.name or ''
            location_name = (
                    rep_profile.location_id.complete_name
                    or getattr(rep_profile.location_id, 'display_name', None)
                    or rep_profile.location_id.name
                    or ''
            )

            # ---------- إعدادات ----------
            sizes = _parse_image_sizes(request.params.get('image_sizes'))
            prefer_variant = (str(request.params.get('image_source', 'variant')).lower() != 'template')
            include_b64 = str(request.params.get('include_b64', 'false')).lower() in ('1', 'true', 'yes')

            include_flat = str(request.params.get('include_flat', 'false')).lower() in ('1', 'true', 'yes')
            include_groups = str(request.params.get('include_groups', 'false')).lower() in ('1', 'true', 'yes')

            # افتراضيًا: فقط الموجود فعلاً في سيارة المندوب
            only_in_user_car = str(request.params.get('include_zero', 'false')).lower() not in ('1', 'true', 'yes')

            # NEW: فلترة قائمة MSL فقط
            msl_only = str(request.params.get('msl_only', 'false')).lower() in ('1', 'true', 'yes')

            # ---------- تحديد المنتجات الموجودة في سيارة المندوب ----------
            Product = env['product.product'].sudo()
            Quant = env['stock.quant'].sudo()

            quants = Quant.search([('location_id', '=', location_id)])
            product_ids_in_car = {q.product_id.id for q in quants}

            if only_in_user_car:
                if not product_ids_in_car:
                    payload = {
                        "total": 0,
                        "rep_profile": {
                            "user_id": current_user.id,
                            "user_name": user_name,
                            "location_id": location_id,
                            "location_name": location_name,
                            "info_banner_ar": f"المستخدم ({user_name}) مسؤول عن المستودع ({location_name})"
                        },
                        "filters": {
                            "only_in_user_car": True,
                            "msl_only": msl_only,
                        },
                        "categories": []
                    }
                    return format_response(True, "Products fetched successfully", payload, http_status=200)
                products = Product.search([('id', 'in', list(product_ids_in_car))])
            else:
                products = Product.search([])

            # NEW: طبّق فلترة الـ MSL
            if msl_only:
                try:
                    products = products.filtered(lambda p: bool(getattr(p, 'msl_flag', False)))
                except Exception:
                    pass

            # ---------- كميات سيارة المندوب ----------
            qty_by_product = defaultdict(float)
            if products:
                quants_for_products = Quant.search([
                    ('location_id', '=', location_id),
                    ('product_id', 'in', products.ids)
                ])
                for q in quants_for_products:
                    qty_by_product[q.product_id.id] += q.available_quantity

            # ---------- تهيئة منطق قوائم الأسعار ----------
            PricelistItem = env['product.pricelist.item'].sudo()
            today = fields.Date.context_today(current_user)

            ON_GLOBAL = ('3_global', 'global', 'all')

            base_date_domain = [
                '|', ('date_start', '=', False), ('date_start', '<=', today),
                '|', ('date_end', '=', False), ('date_end', '>=', today),
            ]

            global_items = PricelistItem.search(base_date_domain + [
                ('applied_on', 'in', ON_GLOBAL),
            ])
            global_pl_ids = set(global_items.mapped('pricelist_id').ids)

            def _product_prices(prod):
                item_domain = [
                    '|', ('date_start', '=', False), ('date_start', '<=', today),
                    '|', ('date_end', '=', False), ('date_end', '>=', today),
                    '|', ('product_id', '=', prod.id),
                    '|', ('product_tmpl_id', '=', prod.product_tmpl_id.id),
                    '|', ('categ_id', 'parent_of', prod.categ_id.id),
                    ('applied_on', 'in', ON_GLOBAL)
                ]

                applicable_items = PricelistItem.search(item_domain)
                prices = []

                for item in applicable_items:
                    pl = item.pricelist_id
                    if not pl or not pl.active:
                        continue

                    current_price = prod.list_price
                    if item.compute_price == 'fixed':
                        current_price = item.fixed_price
                    elif item.compute_price == 'percentage':
                        current_price = prod.list_price * (1 - (item.percent_price / 100.0))
                    elif item.compute_price == 'formula':
                        base_price = prod.list_price
                        current_price = base_price * (1 - (item.price_discount / 100.0)) + item.price_surcharge

                    compute_price_raw = item.compute_price
                    prices.append({
                        "pricelist_id": pl.id,
                        "pricelist_name": noneify(pl.name),
                        "price": current_price,
                        "rule_id": item.id,
                        "min_quantity": item.min_quantity or 0.0,
                        "compute_price": 'percentage' if compute_price_raw == 'percent' else compute_price_raw,
                        "compute_price_raw": noneify(compute_price_raw),
                        "percent_price": item.percent_price if compute_price_raw in ('percent', 'percentage') else 0.0,
                    })

                if not prices:
                    prices.append({
                        "pricelist_id": 0,
                        "pricelist_name": "Default Price",
                        "price": prod.list_price,
                        "rule_id": False,
                        "min_quantity": 0.0,
                        "compute_price": "list_price",
                        "compute_price_raw": "list_price",
                        "percent_price": 0.0
                    })

                prices.sort(key=lambda x: (x['pricelist_name'] or '', x['min_quantity']))
                return prices

            _ = products.mapped('product_tmpl_id')

            # ---------- مولد وسائط المنتج ----------
            def _product_media(prod):
                image_urls = _product_image_urls(prod, sizes, prefer_variant=prefer_variant)
                thumbnail_url = image_urls.get(str(min(sizes))) or next(iter(image_urls.values()), None)
                image_b64_128 = None
                if include_b64:
                    prod_full = prod.with_context(bin_size=False)
                    tmpl_full = prod.product_tmpl_id.with_context(bin_size=False) if prod.product_tmpl_id else None
                    use_prod_src = bool(
                        getattr(prod_full, 'image_1920', False) or getattr(prod_full, 'image_128', False))
                    src = prod_full if use_prod_src else tmpl_full
                    if src is not None:
                        b64_val = getattr(src, 'image_128', False) or getattr(src, 'image_1920', False)
                        if b64_val:
                            try:
                                image_b64_128 = (
                                    b64_val.decode('utf-8') if isinstance(b64_val, (bytes, bytearray)) else str(b64_val)
                                )
                            except Exception:
                                image_b64_128 = str(b64_val)
                return image_urls, thumbnail_url, image_b64_128

            # ---------- بناء عناصر المنتجات (مسطّح) ----------
            flat_products = []
            for prod in products:
                qty_in_car = float(qty_by_product.get(prod.id, 0.0))
                if only_in_user_car and qty_in_car <= 0.0:
                    continue

                qty_total = float(prod.free_qty or 0.0)
                qty_other = max(qty_total - qty_in_car, 0.0)

                prices_json = _product_prices(prod)
                image_urls, thumbnail_url, image_b64_128 = _product_media(prod)
                categ = prod.categ_id

                prod_msl = bool(getattr(prod, 'msl_flag', False))
                categ_msl = bool(getattr(categ, 'msl_flag', False)) if categ else False

                flat_products.append({
                    "id": prod.id,
                    "name": noneify(prod.name),
                    "default_code": noneify(prod.default_code),
                    "sales_channels": [{"id": c.id, "name": c.name} for c in prod.sales_channel_ids],
                    "list_price": prod.list_price,
                    "consumer_price": float(getattr(prod, 'consumer_price', 0.0) or 0.0),
                    "qty_in_user_location": qty_in_car,
                    "qty_in_all_locations": qty_other,
                    "is_in_user_location": qty_in_car > 0,
                    "prices": prices_json,
                    "image_url": noneify(thumbnail_url),
                    "image_urls": {k: noneify(v) for k, v in image_urls.items()},
                    "image_128_b64": noneify(image_b64_128) if include_b64 else None,
                    "msl_flag": prod_msl,
                    "category": {
                        "id": categ.id if categ else 0,
                        "name": noneify(
                            getattr(categ, 'display_name', None) or getattr(categ, 'name', None) or "Uncategorized"),
                        "msl_flag": categ_msl,
                    },
                })

            # ---------- فرز وتجميع المنتجات ----------
            flat_products.sort(
                key=lambda p: (
                    p['qty_in_user_location'] == 0,
                    -float(p['qty_in_user_location'] or 0.0),
                    (p['name'] or '').lower()
                )
            )

            by_leaf_cat = {}
            for item in flat_products:
                cat = item["category"] or {}
                cid = cat.get("id", 0)
                if cid not in by_leaf_cat:
                    by_leaf_cat[cid] = {
                        "category": {
                            "id": cid,
                            "name": noneify(cat.get("name") or "Uncategorized"),
                            "msl_flag": bool(cat.get("msl_flag", False)),
                        },
                        "qty_total_in_user_location": 0.0,
                        "product_count": 0,
                        "products": []
                    }
                by_leaf_cat[cid]["products"].append(item)
                by_leaf_cat[cid]["qty_total_in_user_location"] += float(item.get("qty_in_user_location") or 0.0)
                by_leaf_cat[cid]["product_count"] += 1

            leaf_categories = list(by_leaf_cat.values())
            for node in leaf_categories:
                node["products"].sort(
                    key=lambda it: (
                        it["qty_in_user_location"] == 0,
                        -float(it["qty_in_user_location"] or 0.0),
                        (it["name"] or '').lower()
                    )
                )
            leaf_categories.sort(
                key=lambda n: (-float(n["qty_total_in_user_location"] or 0.0), (n["category"]["name"] or ""))
            )

            simple_groups = []
            if include_groups:
                simple_groups = [
                    {
                        "category": node["category"],
                        "qty_total_in_user_location": node["qty_total_in_user_location"],
                        "products": node["products"],
                        "product_count": node["product_count"]
                    }
                    for node in leaf_categories
                ]

            # ---------- بناء payload ----------
            payload = {
                "total": len(flat_products),
                "rep_profile": {
                    "user_id": current_user.id,
                    "user_name": user_name,
                    "location_id": location_id,
                    "location_name": location_name,
                    "info_banner_ar": f"المستخدم ({user_name}) مسؤول عن المستودع ({location_name})"
                },
                "filters": {
                    "only_in_user_car": only_in_user_car,
                    "msl_only": msl_only,
                },
                "categories": leaf_categories
            }

            if include_flat:
                payload["products"] = flat_products
            if include_groups:
                payload["groups"] = simple_groups

            # ---------- تبويب مواد المستودع الرئيسي ----------
            main_stock_categories = []
            main_stock_count = 0  # متغير لحساب العدد الكلي
            try:
                _logger.info("Fetching and grouping all products for main stock...")

                # جلب كل المنتجات (مخزنية واستهلاكية) وإلغاء الاستثناءات
                products_to_show = env['product.product'].sudo().search([
                    ('type', 'in', ['consu']),
                    ('active', '=', True)
                ])

                # حساب العدد الكلي للمواد
                main_stock_count = len(products_to_show)

                main_by_leaf_cat = {}

                for prod in products_to_show:
                    tmpl = prod.product_tmpl_id
                    categ = tmpl.categ_id if tmpl else None
                    cid = categ.id if categ else 0

                    image_urls = _product_image_urls(prod, sizes)
                    prices_json = _product_prices(prod)

                    # بناء بيانات المنتج
                    prod_data = {
                        "id": prod.id,
                        "name": noneify(prod.name),
                        "default_code": noneify(prod.default_code),
                        "sales_channels": [{"id": c.id, "name": c.name} for c in prod.sales_channel_ids],
                        "list_price": prod.list_price,
                        "consumer_price": float(getattr(prod, 'consumer_price', 0.0) or 0.0),
                        "qty_in_user_location": 0.0,
                        "qty_in_all_locations": 0.0,
                        "is_in_user_location": False,
                        "prices": prices_json,
                        "image_url": image_urls.get(str(min(sizes))),
                        "image_urls": image_urls,
                        "msl_flag": bool(getattr(prod, 'msl_flag', False)),
                        "category": {
                            "id": cid,
                            "name": noneify(getattr(categ, 'display_name', None) or getattr(categ, 'name',
                                                                                            None) or "Uncategorized"),
                            "msl_flag": bool(getattr(categ, 'msl_flag', False)) if categ else False,
                        },
                    }

                    # منطق التجميع (Grouping)
                    if cid not in main_by_leaf_cat:
                        main_by_leaf_cat[cid] = {
                            "category": prod_data["category"],
                            "qty_total_in_user_location": 0.0,
                            "product_count": 0,
                            "products": []
                        }

                    main_by_leaf_cat[cid]["products"].append(prod_data)
                    main_by_leaf_cat[cid]["product_count"] += 1

                # تحويل القاموس إلى قائمة وفرزها حسب اسم التصنيف
                main_stock_categories = list(main_by_leaf_cat.values())
                for node in main_stock_categories:
                    node["products"].sort(key=lambda it: (it['name'] or '').lower())

                main_stock_categories.sort(key=lambda n: (n["category"]["name"] or ""))

                _logger.info("Total main stock categories added: %s", len(main_stock_categories))

            except Exception as e:
                _logger.warning("Failed fetching main stock products. Exception: %s", str(e))

            # تحديث الـ Payload
            payload["main_stock_materials"] = main_stock_categories
            # إضافة العدد الكلي للمواد هنا
            payload["main_stock_total"] = main_stock_count

            return format_response(True, "Products fetched successfully", payload, http_status=200)

        except Exception as e:
            _logger.exception("Error fetching products")
            return format_response(False, f"Internal error: {str(e)}", error_code=-500, http_status=500)
    # ----------------------------------------------------------------------
    # Customers
    # ----------------------------------------------------------------------
    @http.route([
        '/sales_rep_manager/<string:api_version>/customers',
        '/sales_rep_manager/<string:api_version>/get_customers',
    ], type='http', auth='none', methods=['GET', 'OPTIONS'], csrf=False, cors="*")
    @jwt_required()
    def get_customers(self, **kwargs):
        if request.httprequest.method == 'OPTIONS':
            return request.make_response(
                headers=[('Content-Type', 'application/json')],
                data=json.dumps({"ok": True}),
                status=200
            )

        try:
            env = kwargs["_jwt_env"]
            current_user = env['res.users'].browse(kwargs["_jwt_user_id"])
            PartnerModel = env['res.partner'].sudo()
            PricelistModel = env['product.pricelist'].sudo()

            # ======= جلب ملف المندوب =======
            rep_profiles = env['sales.rep.profile'].sudo().search([('user_id', '=', current_user.id)])
            if not rep_profiles:
                return format_response(False, "No profile found for this user", data={"total": 0, "customers": []})

            # ======= معالجة كل ملف مندوب =======
            customers = PartnerModel.browse()  # فارغ
            for profile in rep_profiles:
                if not profile.route_id:
                    return format_response(False, "No route assigned for this profile",
                                           data={"total": 0, "customers": []})
                if profile.route_id.partner_ids:
                    customers |= profile.route_id.partner_ids

            if not customers:
                return format_response(False, "No customers found for this route", data={"total": 0, "customers": []})

            # ======= بناء قائمة العملاء =======
            try:
                pl_map = PricelistModel._get_partner_pricelist_multi(customers.ids)
            except Exception:
                pl_map = {c.id: c.property_product_pricelist for c in customers}

            customer_list = []
            for cust in customers:
                pl = pl_map.get(cust.id)
                customer_list.append({
                    "id": cust.id,
                    "email": noneify(cust.email),
                    "phone": noneify(cust.phone),
                    "areas": noneify(" - ".join(filter(None, [cust.city, cust.street]))),
                    "name": noneify(cust.name),
                    "governorate": cust.state_id.name or "",
                    "customer_classification": noneify(getattr(cust, "customer_classification", None)),
                    "credit": cust.credit or 0.0,  # إجمالي المبلغ المستحق (Receivable)
                    "use_partner_credit_limit": cust.use_partner_credit_limit or False,  # هل تفعيل حد الائتمان مفعل؟
                    "credit_limit": cust.credit_limit or 0.0,  # قيمة حد الائتمان
                    "industry": ({
                                     "id": cust.industry_id.id,
                                     "name": noneify(cust.industry_id.name),
                                     "full_name": noneify(getattr(cust.industry_id, "full_name", None)),
                                 } if cust.industry_id else None),
                    "pricelist": ({
                                      "id": pl.id,
                                      "name": noneify(getattr(pl, 'display_name', pl.name)),
                                      "currency": noneify(pl.currency_id.name) if pl and pl.currency_id else None
                                  } if pl else None),
                    "pricelist_property_raw": ({
                                                   "id": cust.property_product_pricelist.id,
                                                   "name": noneify(cust.property_product_pricelist.name)
                                               } if cust.property_product_pricelist else None),
                    "partner_latitude": cust.partner_latitude,
                    "partner_longitude": cust.partner_longitude,
                })

            return format_response(True, "Customers fetched successfully", {
                "total": len(customers),
                "customers": customer_list
            }, http_status=200)

        except Exception as e:
            _logger.exception("Error fetching customers")
            return format_response(False, f"Internal error: {str(e)}", error_code=-500,
                                   http_status=500)  # Sale Orders (list)

    # ----------------------------------------------------------------------
    @http.route(
        '/sales_rep_manager/<string:api_version>/sale_orders',
        type='http', auth='none', methods=['GET', 'OPTIONS'], csrf=False, cors="*"
    )
    @jwt_required()
    def get_sale_orders(self, **kwargs):
        if request.httprequest.method == 'OPTIONS':
            return json_response({"ok": True}, status=200)

        try:
            env = kwargs["_jwt_env"]
            current_user = env['res.users'].browse(kwargs["_jwt_user_id"])
            SaleOrder = env['sale.order'].sudo()

            sale_orders = SaleOrder.search([('user_id', '=', current_user.id)])

            orders_list = []
            for order in sale_orders:
                lines = []
                for l in order.order_line:
                    lines.append({
                        "line_id": l.id,
                        "product_id": l.product_id.id,
                        "product_name": noneify(l.product_id.display_name),
                        "quantity": l.product_uom_qty,
                        "uom": noneify(l.product_uom.display_name) if l.product_uom else None,
                        "price_unit": l.price_unit,
                        "discount": l.discount,  # %
                        "subtotal": l.price_subtotal,  # بدون ضريبة
                        "tax": l.price_tax,  # قيمة الضريبة
                        "total": l.price_total,  # مع الضريبة
                        "taxes": [
                            {"id": t.id, "name": noneify(t.name), "amount": t.amount, "type": noneify(t.amount_type)}
                            for t in l.tax_id],
                        "name": noneify(l.name),
                    })

                orders_list.append({
                    "id": order.id,
                    "name": noneify(order.name),
                    "partner_id": order.partner_id.id,
                    "partner_name": noneify(order.partner_id.name),
                    "date_order": order.date_order.strftime('%Y-%m-%d %H:%M:%S') if order.date_order else None,
                    "currency": noneify(order.currency_id.name),
                    "amount_untaxed": order.amount_untaxed,
                    "amount_tax": order.amount_tax,
                    "amount_total": order.amount_total,
                    "state": noneify(order.state),
                    "user": {"id": order.user_id.id, "name": noneify(order.user_id.name) if order.user_id else None},
                    "lines_count": len(lines),
                    "lines": lines,
                })

            return format_response(True, "Sale orders fetched successfully", {
                "total": len(sale_orders),
                "sale_orders": orders_list
            }, http_status=200)

        except Exception as e:
            _logger.exception("Error fetching sale orders")
            return format_response(False, f"Internal error: {str(e)}", error_code=-500, http_status=500)

    # ----------------------------------------------------------------------
    # Route Lines
    # ----------------------------------------------------------------------
    @http.route(
        '/sales_rep_manager/<string:api_version>/route_lines',
        type='http', auth='none', methods=['GET', 'OPTIONS'], csrf=False, cors="*"
    )
    @jwt_required()
    def get_route_lines(self, **kwargs):
        if request.httprequest.method == 'OPTIONS':
            return json_response({"ok": True}, status=200)

        try:
            env = kwargs["_jwt_env"]
            current_user = env['res.users'].browse(kwargs["_jwt_user_id"])

            # بروفايل المندوب الحالي
            rep_profile = env['sales.rep.profile'].sudo().search([
                ('user_id', '=', current_user.id)
            ], limit=1)

            if not rep_profile or not rep_profile.route_id:
                return format_response(
                    False,
                    "No route assigned to this sales representative",
                    error_code=-404,
                    http_status=404
                )

            route = rep_profile.route_id

            route_data = {
                "id": route.id,
                "route_number": noneify(route.route_number),
                "route_name": noneify(route.route_name),
                "governorate": ({
                                    "id": route.governorate_id.id,
                                    "name": noneify(route.governorate_id.name),
                                } if route.governorate_id else None),
                "areas": [{"id": a.id, "name": noneify(a.name)} for a in route.area_ids],
                "sales_channels": [{"id": ch.id, "name": noneify(ch.name)} for ch in route.sales_channel_ids],
                "partners": [{"id": p.id, "name": noneify(p.name), "city": noneify(p.city)} for p in route.partner_ids],
            }

            return format_response(True, "Route fetched successfully", {
                "total": 1,
                "route_lines": [route_data]
            }, http_status=200)

        except Exception as e:
            _logger.exception("Error fetching route lines")
            return format_response(False, f"Internal error: {str(e)}", error_code=-500, http_status=500)

    # ----------------------------------------------------------------------
    # Invoices: قائمة الفواتير للمستخدم الحالي
    # ----------------------------------------------------------------------
    @http.route([
        '/sales_rep_manager/<string:api_version>/invoices',
        '/sales_rep_manager/<string:api_version>/get_invoices',
    ], type='http', auth='none', methods=['GET', 'OPTIONS'], csrf=False, cors="*")
    @jwt_required()
    def get_invoices(self, **kwargs):
        if request.httprequest.method == 'OPTIONS':
            return json_response({"ok": True}, status=200)

        try:
            env = kwargs["_jwt_env"]
            current_user = env['res.users'].browse(kwargs["_jwt_user_id"])
            Move = env['account.move'].sudo()

            # ترقيم صفحات + مرشحات اختيارية
            limit = int(request.params.get('limit', 50))
            offset = int(request.params.get('offset', 0))
            state = request.params.get('state')  # draft, posted, cancel/ canceled
            date_from = _parse_date(request.params.get('date_from'))
            date_to = _parse_date(request.params.get('date_to'))

            domain = [
                ('move_type', '=', 'out_invoice'),
                ('invoice_user_id', '=', current_user.id),
            ]
            if state:
                domain.append(('state', '=', state))
            if date_from:
                domain.append(('invoice_date', '>=', date_from.date()))
            if date_to:
                domain.append(('invoice_date', '<=', date_to.date()))

            total_count = Move.search_count(domain)
            invoices = Move.search(domain, order='invoice_date desc, id desc', limit=limit, offset=offset)

            base = request.httprequest.host_url.rstrip('/')

            data = []
            for inv in invoices:
                data.append({
                    "id": inv.id,
                    "name": noneify(inv.name or inv.payment_reference or inv.ref),
                    "number": noneify(inv.name),
                    "partner": {
                        "id": inv.partner_id.id,
                        "name": noneify(inv.partner_id.name),
                        "phone": noneify(inv.partner_id.phone),
                        "email": noneify(inv.partner_id.email),
                        "city": noneify(inv.partner_id.city),
                    },
                    "invoice_date": inv.invoice_date and inv.invoice_date.strftime('%Y-%m-%d') or None,
                    "currency": noneify(inv.currency_id.name) if inv.currency_id else None,
                    "state": noneify(inv.state),
                    "amount_untaxed": inv.amount_untaxed,
                    "amount_tax": inv.amount_tax,
                    "amount_total": inv.amount_total,
                    "links": {
                        "pdf": noneify(f"{base}/report/pdf/account.report_invoice/{inv.id}"),
                        "portal": noneify(f"{base}/my/invoices/{inv.id}"),
                        "form": noneify(f"{base}/web#id={inv.id}&model=account.move&view_type=form"),
                    },
                })

            return format_response(True, "Invoices fetched successfully", {
                "total": total_count,
                "limit": limit,
                "offset": offset,
                "invoices": data
            }, http_status=200)

        except Exception as e:
            _logger.exception("Error fetching invoices list")
            return format_response(False, f"Internal error: {str(e)}", error_code=-500, http_status=500)

    # ----------------------------------------------------------------------
    # Invoice detail by ID: تفاصيل فاتورة واحدة
    # ----------------------------------------------------------------------
    @http.route([
        '/sales_rep_manager/<string:api_version>/invoice/<int:invoice_id>',
    ], type='http', auth='none', methods=['GET', 'OPTIONS'], csrf=False, cors="*")
    @jwt_required()
    def get_invoice_detail(self, invoice_id, **kwargs):
        if request.httprequest.method == 'OPTIONS':
            return json_response({"ok": True}, status=200)

        try:
            env = kwargs["_jwt_env"]
            current_user = env['res.users'].browse(kwargs["_jwt_user_id"])
            include_images = _parse_bool(request.params.get('include_images'), default=True)
            image_sizes = tuple(
                int(s.strip()) for s in str(request.params.get('image_sizes', '128,256')).split(',')
                if s.strip().isdigit()
            )

            Move = env['account.move'].sudo()
            inv = Move.browse(invoice_id)
            if not inv.exists() or inv.move_type != 'out_invoice':
                return format_response(False, "Invoice not found", error_code=-404, http_status=404)

            # أمان: السماح فقط بفواتير المندوب نفسه
            if inv.invoice_user_id.id != current_user.id:
                return format_response(False, "Access denied to this invoice", error_code=-403, http_status=403)

            # ======== ترويسة عربية (كما في التصميم) ========
            cur_name = (inv.currency_id and (inv.currency_id.name or '') or '').upper()
            cur_symbol = (inv.currency_id and (getattr(inv.currency_id, 'symbol', '') or '') or '').strip()
            currency_ar = None
            if cur_name in ('SYP', 'SYR') or ('ل.س' in cur_symbol or 'ليرة' in cur_symbol):
                currency_ar = 'الليرة السورية'
            elif cur_name == 'USD' or ('$' in cur_symbol):
                currency_ar = 'الدولار الأمريكي'
            else:
                currency_ar = noneify(inv.currency_id.name) if inv.currency_id else None

            header_ar = {
                "اسم الزبون": noneify(inv.partner_id.name),
                "رقم الفاتورة": noneify(inv.name),
                "تاريخ الفاتورة": inv.invoice_date and inv.invoice_date.strftime('%Y-%m-%d') or None,
                "العملة المستعملة": currency_ar,
            }

            # ======== أسطر الفاتورة (جدول عربي كما بالصورة) ========
            lines_ar = []
            discount_by_category = {}  # {categ_name: {"percent_samples": [], "discount_total": float}}
            total_wo_tax = 0.0

            for l in inv.invoice_line_ids:
                product = l.product_id
                product_name = product.display_name if product else (l.name or '')
                categ = product.categ_id.name if (product and product.categ_id) else "غير مصنّف"

                # سعر المستهلك من product.template
                consumer_price = None
                try:
                    if product and product.product_tmpl_id and hasattr(product.product_tmpl_id, 'consumer_price'):
                        consumer_price = float(product.product_tmpl_id.consumer_price or 0.0)
                except Exception:
                    consumer_price = None

                qty = float(l.quantity or 0.0)
                price_unit = float(l.price_unit or 0.0)

                line_subtotal = float(l.price_subtotal or (price_unit * qty))
                total_wo_tax += line_subtotal

                price_before_disc = price_unit * qty
                line_discount_amount = price_before_disc * ((float(l.discount or 0.0)) / 100.0)
                agg = discount_by_category.setdefault(categ, {"percent_samples": [], "discount_total": 0.0})
                if l.discount:
                    try:
                        agg["percent_samples"].append(float(l.discount))
                    except Exception:
                        pass
                agg["discount_total"] += line_discount_amount

                images = None
                if include_images and product:
                    images = _product_image_urls(product, sizes=image_sizes, prefer_variant=True)

                lines_ar.append({
                    "المنتج": noneify(product_name),
                    "المبيع": price_unit,
                    "المستهلك": consumer_price,
                    "الكمية": qty,
                    "المجموع": line_subtotal,
                })

            # ملخص الخصومات بالعربي (بالصنف)
            discounts_ar = []
            total_discount = 0.0
            for categ_name, info in discount_by_category.items():
                percent = round(sum(info["percent_samples"]) / len(info["percent_samples"]), 2) if info[
                    "percent_samples"] else 0.0
                amount = float(info["discount_total"] or 0.0)
                total_discount += amount
                discounts_ar.append({
                    "اسم الصنف": noneify(categ_name),
                    "نسبة الخصم": percent,
                    "قيمة الخصم": amount,
                })

            # ======== إجماليات كما في التصميم ========
            totals_ar = {
                "المجموع الكلي": total_wo_tax,
                "مجموع الخصم": total_discount,
                "الإجمالي النهائي": float(inv.amount_total or 0.0),
            }

            base = request.httprequest.host_url.rstrip('/')
            links = {
                "pdf": noneify(f"{base}/report/pdf/account.report_invoice/{inv.id}"),
                "portal": noneify(f"{base}/my/invoices/{inv.id}"),
                "form": noneify(f"{base}/web#id={inv.id}&model=account.move&view_type=form"),
            }

            # إخراج سابق للتوافق الخلفي
            lines_legacy = []
            for l in inv.invoice_line_ids:
                product = l.product_id
                categ = product.categ_id.name if product and product.categ_id else "Uncategorized"
                images = None
                if include_images and product:
                    images = _product_image_urls(product, sizes=image_sizes, prefer_variant=True)
                price_before_disc = (l.price_unit or 0.0) * (l.quantity or 0.0)
                line_discount_amount = price_before_disc * ((l.discount or 0.0) / 100.0)
                lines_legacy.append({
                    "line_id": l.id,
                    "product": {
                        "id": product.id if product else None,
                        "name": noneify(product.display_name if product else (l.name or '')),
                        "default_code": noneify(product.default_code) if product else None,
                        "category": noneify(categ),
                        "images": images or None,
                    },
                    "quantity": l.quantity,
                    "uom": noneify(l.product_uom_id.display_name) if getattr(l, 'product_uom_id', False) else None,
                    "price_unit": l.price_unit,
                    "discount_percent": l.discount,
                    "discount_amount": line_discount_amount,
                    "subtotal_wo_tax": l.price_subtotal,
                    "total_with_tax": l.price_total,
                    "description": noneify(l.name),
                    "taxes": [
                        {"id": t.id, "name": noneify(t.name), "amount": t.amount, "type": noneify(t.amount_type)}
                        for t in l.tax_ids
                    ],
                })

            result = {
                "عربي": {
                    "ترويسة": header_ar,
                    "الأسطر": lines_ar,
                    "الخصومات": discounts_ar,
                    "الإجماليات": totals_ar,
                    "روابط": links,
                },
                "header": {
                    "id": inv.id,
                    "name": noneify(inv.name or inv.payment_reference or inv.ref),
                    "number": noneify(inv.name),
                    "state": noneify(inv.state),
                    "currency": noneify(inv.currency_id.name) if inv.currency_id else None,
                    "invoice_date": inv.invoice_date and inv.invoice_date.strftime('%Y-%m-%d') or None,
                    "partner": {
                        "id": inv.partner_id.id,
                        "name": noneify(inv.partner_id.name),
                        "phone": noneify(inv.partner_id.phone),
                        "email": noneify(inv.partner_id.email),
                        "city": noneify(inv.partner_id.city),
                    },
                    "salesperson": {
                        "id": inv.invoice_user_id.id if inv.invoice_user_id else None,
                        "name": noneify(inv.invoice_user_id.name) if inv.invoice_user_id else None,
                    },
                    "amounts": {
                        "untaxed": inv.amount_untaxed,
                        "tax": inv.amount_tax,
                        "total": inv.amount_total,
                    },
                    "links": links,
                },
                "lines_count": len(inv.invoice_line_ids),
                "lines": lines_legacy,
            }

            if discounts_ar:
                result["discount_by_category"] = [
                    {"category": d["اسم الصنف"], "discount_percent_ref": d["نسبة الخصم"],
                     "discount_amount_total": d["قيمة الخصم"]}
                    for d in discounts_ar
                ]
                result["discount_total_estimated"] = totals_ar["مجموع الخصم"]

            return format_response(True, "Invoice fetched successfully", result, http_status=200)

        except Exception as e:
            _logger.exception("Error fetching invoice detail")
            return format_response(False, f"Internal error: {str(e)}", error_code=-500, http_status=500)

    # ----------------------------------------------------------------------
    # Customer Overview: ملخّص الزبون
    # ----------------------------------------------------------------------
    @http.route([
        '/sales_rep_manager/<string:api_version>/customer/<int:partner_id>/overview',
    ], type='http', auth='none', methods=['GET', 'OPTIONS'], csrf=False, cors="*")
    @jwt_required()
    def get_customer_overview(self, partner_id, **kwargs):
        if request.httprequest.method == 'OPTIONS':
            return json_response({"ok": True}, status=200)

        try:
            env = kwargs["_jwt_env"]
            current_user = env['res.users'].browse(kwargs["_jwt_user_id"])
            Partner = env['res.partner'].sudo()
            Move = env['account.move'].sudo()
            Sale = env['sale.order'].sudo()

            partner = Partner.browse(partner_id)
            if not partner.exists():
                return format_response(False, "Customer not found", error_code=-404, http_status=404)

            allowed_customers = _get_user_route_customers(env, current_user)
            if partner not in allowed_customers:
                return format_response(False, "Access denied to this customer", error_code=-403, http_status=403)

            inv_domain = [
                ('move_type', '=', 'out_invoice'),
                ('partner_id', '=', partner.id),
                ('state', '!=', 'cancel'),
            ]
            last_inv = Move.search(inv_domain, order='invoice_date desc, id desc', limit=1)

            so_domain = [
                ('partner_id', '=', partner.id),
                ('state', 'in', ['sale', 'done', 'sent', 'draft']),
            ]
            last_so = Sale.search(so_domain, order='date_order desc, id desc', limit=1)

            inv_total = sum(Move.search(inv_domain).mapped('amount_total'))
            so_total = sum(Sale.search(so_domain).mapped('amount_total'))

            base_url = request.httprequest.host_url.rstrip('/')

            overview = {
                "customer": {
                    "id": partner.id,
                    "name": noneify(partner.name),
                    "phone": noneify(partner.phone or partner.mobile),
                    "mobile": noneify(partner.mobile),
                    "email": noneify(partner.email),
                    "vat": noneify(partner.vat),
                    "reference": noneify(partner.ref),
                    "address": {
                        "street": noneify(partner.street),
                        "street2": noneify(partner.street2),
                        "city": noneify(partner.city),
                        "state": noneify(partner.state_id.name) if partner.state_id else None,
                        "country": noneify(partner.country_id.name) if partner.country_id else None,
                        "latitude": partner.partner_latitude,
                        "longitude": partner.partner_longitude,
                    },
                },
                "last_invoice": ({
                                     "id": last_inv.id,
                                     "number": noneify(last_inv.name),
                                     "date": last_inv.invoice_date and last_inv.invoice_date.strftime('%Y-%m-%d'),
                                     "amount_total": last_inv.amount_total,
                                     "currency": noneify(last_inv.currency_id.name) if last_inv.currency_id else None,
                                     "links": {
                                         "detail_api": noneify(
                                             f"{base_url}/sales_rep_manager/<string:api_version>/invoice/{last_inv.id}"),
                                         "pdf": noneify(f"{base_url}/report/pdf/account.report_invoice/{last_inv.id}"),
                                     }
                                 } if last_inv else None),
                "last_order": ({
                                   "id": last_so.id,
                                   "name": noneify(last_so.name),
                                   "date": last_so.date_order and last_so.date_order.strftime('%Y-%m-%d %H:%M:%S'),
                                   "amount_total": last_so.amount_total,
                                   "currency": noneify(last_so.currency_id.name) if last_so.currency_id else None,
                                   "links": {
                                       "form": noneify(
                                           f"{base_url}/web#id={last_so.id}&model=sale.order&view_type=form")
                                   }
                               } if last_so else None),
                "totals": {
                    "invoices_total": inv_total,
                    "orders_total": so_total,
                },
                "links": {
                    "all_invoices_api": noneify(
                        f"{base_url}/sales_rep_manager/<string:api_version>/customer/{partner.id}/invoices"),
                    "all_orders_api": noneify(
                        f"{base_url}/sales_rep_manager/<string:api_version>/customer/{partner.id}/orders"),
                }
            }

            return format_response(True, "Customer overview fetched successfully", overview, http_status=200)

        except Exception as e:
            _logger.exception("Error fetching customer overview")
            return format_response(False, f"Internal error: {str(e)}", error_code=-500, http_status=500)

    # ----------------------------------------------------------------------
    # Customer Invoices: كل فواتير الزبون
    # ----------------------------------------------------------------------
    @http.route([
        '/sales_rep_manager/<string:api_version>/customer/<int:partner_id>/invoices',
    ], type='http', auth='none', methods=['GET', 'OPTIONS'], csrf=False, cors="*")
    @jwt_required()
    def get_customer_invoices(self, partner_id, **kwargs):
        if request.httprequest.method == 'OPTIONS':
            return json_response({"ok": True}, status=200)

        try:
            env = kwargs["_jwt_env"]
            current_user = env['res.users'].browse(kwargs["_jwt_user_id"])
            Partner = env['res.partner'].sudo()
            Move = env['account.move'].sudo()

            partner = Partner.browse(partner_id)
            if not partner.exists():
                return format_response(False, "Customer not found", error_code=-404, http_status=404)
            allowed_customers = _get_user_route_customers(env, current_user)
            if partner not in allowed_customers:
                return format_response(False, "Access denied to this customer", error_code=-403, http_status=403)

            limit = int(request.params.get('limit', 50))
            offset = int(request.params.get('offset', 0))
            state = request.params.get('state')
            date_from = request.params.get('date_from')
            date_to = request.params.get('date_to')

            domain = [
                ('move_type', '=', 'out_invoice'),
                ('partner_id', '=', partner.id),
            ]
            if state:
                domain.append(('state', '=', state))
            if date_from:
                domain.append(('invoice_date', '>=', date_from))
            if date_to:
                domain.append(('invoice_date', '<=', date_to))

            total = Move.search_count(domain)
            invoices = Move.search(domain, order='invoice_date desc, id desc', limit=limit, offset=offset)

            base_url = request.httprequest.host_url.rstrip('/')

            data = []
            for inv in invoices:
                data.append({
                    "id": inv.id,
                    "number": noneify(inv.name),
                    "date": inv.invoice_date and inv.invoice_date.strftime('%Y-%m-%d'),
                    "state": noneify(inv.state),
                    "amount_untaxed": inv.amount_untaxed,
                    "amount_tax": inv.amount_tax,
                    "amount_total": inv.amount_total,
                    "currency": noneify(inv.currency_id.name) if inv.currency_id else None,
                    "links": {
                        "detail_api": noneify(f"{base_url}/sales_rep_manager/<string:api_version>/invoice/{inv.id}"),
                        "pdf": noneify(f"{base_url}/report/pdf/account.report_invoice/{inv.id}"),
                    },
                })

            return format_response(True, "Customer invoices fetched successfully", {
                "total": total,
                "limit": limit,
                "offset": offset,
                "invoices": data
            }, http_status=200)

        except Exception as e:
            _logger.exception("Error fetching customer invoices")
            return format_response(False, f"Internal error: {str(e)}", error_code=-500, http_status=500)

    # ----------------------------------------------------------------------
    # Customer Orders: كل طلبيات الزبون
    # ----------------------------------------------------------------------
    @http.route([
        '/sales_rep_manager/<string:api_version>/customer/<int:partner_id>/orders',
    ], type='http', auth='none', methods=['GET', 'OPTIONS'], csrf=False, cors="*")
    @jwt_required()
    def get_customer_orders(self, partner_id, **kwargs):
        if request.httprequest.method == 'OPTIONS':
            return json_response({"ok": True}, status=200)

        try:
            env = kwargs["_jwt_env"]
            current_user = env['res.users'].browse(kwargs["_jwt_user_id"])
            Partner = env['res.partner'].sudo()
            Sale = env['sale.order'].sudo()

            partner = Partner.browse(partner_id)
            if not partner.exists():
                return format_response(False, "Customer not found", error_code=-404, http_status=404)
            allowed_customers = _get_user_route_customers(env, current_user)
            if partner not in allowed_customers:
                return format_response(False, "Access denied to this customer", error_code=-403, http_status=403)

            limit = int(request.params.get('limit', 50))
            offset = int(request.params.get('offset', 0))
            state = request.params.get('state')
            date_from = request.params.get('date_from')
            date_to = request.params.get('date_to')

            domain = [('partner_id', '=', partner.id)]
            if state:
                domain.append(('state', '=', state))
            if date_from:
                domain.append(('date_order', '>=', date_from))
            if date_to:
                domain.append(('date_order', '<=', date_to))

            total = Sale.search_count(domain)
            orders = Sale.search(domain, order='date_order desc, id desc', limit=limit, offset=offset)

            base_url = request.httprequest.host_url.rstrip('/')

            data = []
            for so in orders:
                data.append({
                    "id": so.id,
                    "name": noneify(so.name),
                    "date": so.date_order and so.date_order.strftime('%Y-%m-%d %H:%M:%S'),
                    "state": noneify(so.state),
                    "amount_untaxed": so.amount_untaxed,
                    "amount_tax": so.amount_tax,
                    "amount_total": so.amount_total,
                    "currency": noneify(so.currency_id.name) if so.currency_id else None,
                    "links": {
                        "form": noneify(f"{base_url}/web#id={so.id}&model=sale.order&view_type=form")
                    },
                })

            return format_response(True, "Customer orders fetched successfully", {
                "total": total,
                "limit": limit,
                "offset": offset,
                "orders": data
            }, http_status=200)

        except Exception as e:
            _logger.exception("Error fetching customer orders")
            return format_response(False, f"Internal error: {str(e)}", error_code=-500, http_status=500)

    # ----------------------------------------------------------------------
    # Sale Order detail by ID: تفاصيل أمر بيع واحد
    # ----------------------------------------------------------------------
    @http.route([
        '/sales_rep_manager/<string:api_version>/sale_order/<int:order_id>',
    ], type='http', auth='none', methods=['GET', 'OPTIONS'], csrf=False, cors="*")
    @jwt_required()
    def get_sale_order_detail(self, order_id, **kwargs):
        if request.httprequest.method == 'OPTIONS':
            return json_response({"ok": True}, status=200)

        try:
            env = kwargs["_jwt_env"]
            current_user = env['res.users'].browse(kwargs["_jwt_user_id"])
            include_images = _parse_bool(request.params.get('include_images'), default=True)
            image_sizes = tuple(
                int(s.strip()) for s in str(request.params.get('image_sizes', '128,256')).split(',') if
                s.strip().isdigit()
            )

            Sale = env['sale.order'].sudo()
            order = Sale.browse(order_id)
            if not order.exists():
                return format_response(False, "Sale order not found", error_code=-404, http_status=404)

            if order.user_id.id != current_user.id:
                return format_response(False, "Access denied to this sale order", error_code=-403, http_status=403)

            lines = []
            discount_by_category = {}  # {categ_name: {"percent_samples": [], "discount_total": float}}

            for l in order.order_line:
                product = l.product_id
                categ = product.categ_id.name if product and product.categ_id else "Uncategorized"

                price_before_disc = (l.price_unit or 0.0) * (l.product_uom_qty or 0.0)
                line_discount_amount = price_before_disc * ((l.discount or 0.0) / 100.0)

                agg = discount_by_category.setdefault(categ, {"percent_samples": [], "discount_total": 0.0})
                if l.discount:
                    agg["percent_samples"].append(float(l.discount))
                agg["discount_total"] += line_discount_amount

                images = None
                if include_images and product:
                    images = _product_image_urls(product, sizes=image_sizes, prefer_variant=True)

                lines.append({
                    "line_id": l.id,
                    "product": {
                        "id": product.id if product else None,
                        "name": noneify(product.display_name if product else (l.name or '')),
                        "default_code": noneify(product.default_code) if product else None,
                        "category": noneify(categ),
                        "images": images or None,
                    },
                    "quantity": l.product_uom_qty,
                    "uom": noneify(l.product_uom.display_name) if l.product_uom else None,
                    "price_unit": l.price_unit,
                    "discount_percent": l.discount,
                    "discount_amount": line_discount_amount,
                    "subtotal_wo_tax": l.price_subtotal,
                    "tax": l.price_tax,
                    "total_with_tax": l.price_total,
                    "description": noneify(l.name),
                    "taxes": [
                        {"id": t.id, "name": noneify(t.name), "amount": t.amount, "type": noneify(t.amount_type)}
                        for t in l.tax_id
                    ],
                })

            discount_summary = []
            for categ_name, info in discount_by_category.items():
                percent = round(sum(info["percent_samples"]) / len(info["percent_samples"]), 2) if info[
                    "percent_samples"] else 0.0
                discount_summary.append({
                    "category": noneify(categ_name),
                    "discount_percent_ref": percent,
                    "discount_amount_total": info["discount_total"],
                })

            base = request.httprequest.host_url.rstrip('/')
            header = {
                "id": order.id,
                "name": noneify(order.name),
                "state": noneify(order.state),
                "currency": noneify(order.currency_id.name) if order.currency_id else None,
                "date_order": order.date_order and order.date_order.strftime('%Y-%m-%d %H:%M:%S') or None,
                "partner": {
                    "id": order.partner_id.id,
                    "name": noneify(order.partner_id.name),
                    "phone": noneify(order.partner_id.phone),
                    "email": noneify(order.partner_id.email),
                    "city": noneify(order.partner_id.city),
                },
                "salesperson": {
                    "id": order.user_id.id if order.user_id else None,
                    "name": noneify(order.user_id.name) if order.user_id else None,
                },
                "amounts": {
                    "untaxed": order.amount_untaxed,
                    "tax": order.amount_tax,
                    "total": order.amount_total,
                },
                "links": {
                    "pdf": noneify(f"{base}/report/pdf/sale.report_saleorder/{order.id}"),
                    "form": noneify(f"{base}/web#id={order.id}&model=sale.order&view_type=form"),
                },
            }

            return format_response(True, "Sale order fetched successfully", {
                "header": header,
                "lines_count": len(lines),
                "lines": lines,
                "discount_by_category": discount_summary,
                "discount_total_estimated": sum(
                    x["discount_amount_total"] for x in discount_summary) if discount_summary else 0.0,
            }, http_status=200)

        except Exception as e:
            _logger.exception("Error fetching sale order detail")
            return format_response(False, f"Internal error: {str(e)}", error_code=-500, http_status=500)

    # ----------------------------------------------------------------------
    # Customer Sales by category: مبيعات الزبون حسب التصنيف (من الفواتير المنشورة)
    # ----------------------------------------------------------------------
    @http.route([
        '/sales_rep_manager/<string:api_version>/customer/<int:partner_id>/sales',
    ], type='http', auth='none', methods=['GET', 'OPTIONS'], csrf=False, cors="*")
    @jwt_required()
    def get_customer_sales_by_category(self, partner_id, **kwargs):
        if request.httprequest.method == 'OPTIONS':
            return json_response({"ok": True}, status=200)

        try:
            env = kwargs["_jwt_env"]
            current_user = env['res.users'].browse(kwargs["_jwt_user_id"])
            Partner = env['res.partner'].sudo()
            MoveLine = env['account.move.line'].sudo()

            date_from = _parse_date(request.params.get('date_from'))
            date_to = _parse_date(request.params.get('date_to'))
            q = (request.params.get('q') or '').strip()

            partner = Partner.browse(partner_id)
            if not partner.exists():
                return format_response(False, "Customer not found", error_code=-404, http_status=404)
            allowed_customers = _get_user_route_customers(env, current_user)
            if partner not in allowed_customers:
                return format_response(False, "Access denied to this customer", error_code=-403, http_status=403)

            domain = [
                ('move_id.move_type', '=', 'out_invoice'),
                ('move_id.state', '=', 'posted'),
                ('move_id.partner_id', '=', partner.id),
                ('move_id.invoice_user_id', '=', current_user.id),
                ('product_id', '!=', False),
            ]
            if date_from:
                domain.append(('move_id.invoice_date', '>=', date_from.date()))
            if date_to:
                domain.append(('move_id.invoice_date', '<=', date_to.date()))
            if q:
                domain += ['|', ('product_id.name', 'ilike', q), ('product_id.default_code', 'ilike', q)]

            lines = MoveLine.search(domain)

            groups = {}
            grand_total = 0.0
            for l in lines:
                prod = l.product_id
                categ = prod.categ_id.name if prod and prod.categ_id else "غير مصنّف"
                item = {
                    "product_id": prod.id,
                    "product_name": noneify(prod.display_name),
                    "quantity": l.quantity,
                }
                g = groups.setdefault(categ, {"subtotal": 0.0, "items": []})
                g["items"].append(item)
                g["subtotal"] += (l.price_subtotal or 0.0)
                grand_total += (l.price_subtotal or 0.0)

            grouped = []
            for categ, data in groups.items():
                data["items"].sort(key=lambda x: (x["quantity"] or 0), reverse=True)
                grouped.append({
                    "category": noneify(categ),
                    "products": data["items"],
                    "subtotal_wo_tax": data["subtotal"],
                })
            grouped.sort(key=lambda x: x["subtotal_wo_tax"], reverse=True)

            return format_response(True, "Customer sales fetched successfully", {
                "period": {
                    "from": date_from and date_from.strftime('%Y-%m-%d'),
                    "to": date_to and date_to.strftime('%Y-%m-%d'),
                },
                "currency": noneify(current_user.company_id.currency_id.name),
                "groups": grouped,
                "grand_total_wo_tax": grand_total
            }, http_status=200)

        except Exception as e:
            _logger.exception("Error fetching customer sales")
            return format_response(False, f"Internal error: {str(e)}", error_code=-500, http_status=500)

    # ----------------------------------------------------------------------
    # Statement Details: تفاصيل كشف الحساب (قائمة الفواتير)
    # ----------------------------------------------------------------------

    @http.route([
        '/sales_rep_manager/<string:api_version>/customer/<int:partner_id>/statement/details',
    ], type='http', auth='none', methods=['GET', 'OPTIONS'], csrf=False, cors="*")
    @jwt_required()
    def get_customer_statement_details(self, partner_id, **kwargs):
        if request.httprequest.method == 'OPTIONS':
            return json_response({"ok": True}, status=200)

        try:
            env = kwargs["_jwt_env"]
            Move = env['account.move'].sudo()
            Partner = env['res.partner'].sudo()
            Payment = env['account.payment'].sudo()
            Currency = env['res.currency'].sudo()

            company = env.company

            params = request.params or {}
            date_from_raw = params.get('date_from')
            date_to_raw = params.get('date_to')
            date_from = None
            date_to = None

            if date_from_raw:
                try:
                    date_from = datetime.strptime(date_from_raw, "%Y-%m-%d")
                except:
                    pass
            if date_to_raw:
                try:
                    date_to = datetime.strptime(date_to_raw, "%Y-%m-%d")
                except:
                    pass

            partner = Partner.browse(partner_id)
            if not partner.exists():
                return format_response(False, "Customer not found", error_code=-404, http_status=404)

            target_currency = company.currency_id

            grand_total_invoices = 0.0
            grand_total_paid = 0.0

            def get_display_currency(currency_obj):
                c_name = (currency_obj.name or "").upper()
                c_symbol = (getattr(currency_obj, 'symbol', '') or '')
                if c_name in ("SYP", "SYR", "SP", "S.P") or ("ل.س" in c_symbol):
                    return "S.P"
                elif (c_name == "USD") or ("$" in c_symbol):
                    return "USD"
                return c_name

            inv_domain = [
                ('move_type', 'in', ['out_invoice', 'out_refund']),
                ('state', '=', 'posted'),
                ('partner_id', '=', partner.id),
            ]
            if date_from: inv_domain.append(('invoice_date', '>=', date_from.date()))
            if date_to: inv_domain.append(('invoice_date', '<=', date_to.date()))

            moves = Move.search(inv_domain, order='invoice_date desc, name desc')
            lines = []

            for move in moves:
                is_refund = move.move_type == 'out_refund'
                sign = -1 if is_refund else 1

                amount_total_original = move.amount_total * sign
                amount_residual_original = move.amount_residual * sign
                amount_paid_original = (move.amount_total - move.amount_residual) * sign

                conversion_date = move.invoice_date or fields.Date.today()
                exchange_rate = 1.0

                if move.currency_id != target_currency:
                    exchange_rate = Currency._get_conversion_rate(
                        move.currency_id, target_currency, company, conversion_date
                    )
                    amount_in_company_currency = amount_total_original * exchange_rate
                else:
                    amount_in_company_currency = amount_total_original

                grand_total_invoices += amount_in_company_currency

                lines.append({
                    "رقم": move.name,
                    "تاريخ": str(move.invoice_date),
                    "الكمية": sum(move.invoice_line_ids.mapped('quantity')) * sign,
                    "قيمة الدفعة": round(amount_paid_original, 2),
                    "المتبقي": round(amount_residual_original, 2),
                    "قيمة الفاتورة": round(amount_total_original, 2),
                    "العملة": get_display_currency(move.currency_id)
                })

            pay_domain = [
                ('partner_id', '=', partner.id),
                ('state', 'in', ['paid', 'in_process']),
                ('payment_type', 'in', ['inbound', 'outbound'])
            ]
            if date_from: pay_domain.append(('date', '>=', date_from.date()))
            if date_to: pay_domain.append(('date', '<=', date_to.date()))

            payments = Payment.search(pay_domain)

            for pay in payments:
                amt_original = pay.amount if pay.payment_type == 'inbound' else -pay.amount
                if pay.currency_id != target_currency:
                    rate = Currency._get_conversion_rate(
                        pay.currency_id, target_currency, company, pay.date or fields.Date.today()
                    )
                    amt_in_company_currency = amt_original * rate
                else:
                    amt_in_company_currency = amt_original
                grand_total_paid += amt_in_company_currency

            remaining_total = grand_total_invoices - grand_total_paid
            display_target_currency = get_display_currency(target_currency)

            summary_list = [{
                "العملة": display_target_currency,
                "الفاتورة": round(grand_total_invoices, 2),
                "المدفوع": round(grand_total_paid, 2),
                "المتبقي": round(remaining_total, 2)
            }]

            return format_response(True, "Success", {
                "details": lines,
                "الإجمالي النهائي": summary_list
            }, http_status=200)

        except Exception as e:
            return format_response(False, str(e), error_code=-500, http_status=500)

    # ----------------------------------------------------------------------
    # Statement Stats: إحصائيات كشف الحساب
    # ----------------------------------------------------------------------
    @http.route([
        '/sales_rep_manager/<string:api_version>/customer/<int:partner_id>/statement/stats',
    ], type='http', auth='none', methods=['GET', 'OPTIONS'], csrf=False, cors="*")
    @jwt_required()
    def get_customer_statement_stats(self, partner_id, **kwargs):
        if request.httprequest.method == 'OPTIONS':
            return json_response({"ok": True}, status=200)

        try:
            env = kwargs["_jwt_env"]
            Partner = env['res.partner'].sudo()
            Move = env['account.move'].sudo()
            Sale = env['sale.order'].sudo()
            Payment = env['account.payment'].sudo()

            # معالجة التواريخ لتشمل اليوم بالكامل من 00:00:00 إلى 23:59:59
            date_from = _parse_date(request.params.get('date_from'))
            date_to = _parse_date(request.params.get('date_to'))

            partner = Partner.browse(partner_id)
            if not partner.exists():
                return format_response(False, "Customer not found", error_code=-404, http_status=404)

            # 1. عدد الطلبات (Sale Orders) - التأكد من حالة الطلب
            so_domain = [('partner_id', '=', partner.id), ('state', 'in', ['sale', 'done'])]
            if date_from:
                so_domain.append(('date_order', '>=', datetime.combine(date_from, time.min)))
            if date_to:
                so_domain.append(('date_order', '<=', datetime.combine(date_to, time.max)))

            orders_count = Sale.search_count(so_domain)

            # 2. الفواتير والقطع المباعة والمرتجعة
            inv_refund_domain = [
                ('move_type', 'in', ['out_invoice', 'out_refund']),
                ('state', '=', 'posted'),
                ('partner_id', '=', partner.id)
            ]
            if date_from: inv_refund_domain.append(('invoice_date', '>=', date_from.date()))
            if date_to: inv_refund_domain.append(('invoice_date', '<=', date_to.date()))

            all_moves = Move.search(inv_refund_domain)

            invoices_count = len(all_moves.filtered(lambda m: m.move_type == 'out_invoice'))
            returns_count = len(all_moves.filtered(lambda m: m.move_type == 'out_refund'))

            # --- حساب القطع بشكل منفصل ---
            sold_qty = 0.0
            returned_qty = 0.0

            for move in all_moves:
                # فلترة السطور لجلب المنتجات الحقيقية فقط
                qties = sum(move.invoice_line_ids.filtered(lambda l: l.product_id).mapped('quantity'))
                if move.move_type == 'out_invoice':
                    sold_qty += qties
                elif move.move_type == 'out_refund':
                    returned_qty += qties

            # 3. إجمالي المدخلات (الدفعات)
            pay_domain = [
                ('partner_id', '=', partner.id),
                ('state', 'in', ['paid', 'in_process']),
                ('payment_type', '=', 'inbound')
            ]
            if date_from: pay_domain.append(('date', '>=', date_from.date()))
            if date_to: pay_domain.append(('date', '<=', date_to.date()))

            payments = Payment.search(pay_domain)

            total_syp = total_usd = total_spo = 0.0
            for pay in payments:
                cur_name = (pay.currency_id.name or '').upper()
                cur_symb = (getattr(pay.currency_id, 'symbol', '') or '')
                amt = float(pay.amount or 0.0)
                if cur_name == 'USD' or '$' in cur_symb:
                    total_usd += amt
                elif cur_name == 'SPO':
                    total_spo += amt
                elif cur_name in ('SYP', 'SYR') or any(s in cur_symb for s in ['£', 'ل.س']):
                    total_syp += amt

            stats_ar = {
                "عدد الطلبات": orders_count,
                "عدد الفواتير المفوترة": invoices_count,
                "عدد القطع المباعة": round(sold_qty, 2),
                "عدد القطع المرتجعة": round(returned_qty, 2),
                "إجمالي المدخلات (ليرة)": round(total_syp, 2),
                "إجمالي المدخلات (دولار)": round(total_usd, 2),
                "إجمالي المدخلات (قديم)": round(total_spo, 2),
                "المرتجعات": returns_count,  # عدد الفواتير المرتجعة
            }

            return format_response(True, "Success", {
                "stats_ar": stats_ar,
                "period": {
                    "from": date_from and date_from.strftime('%Y-%m-%d'),
                    "to": date_to and date_to.strftime('%Y-%m-%d'),
                }
            }, http_status=200)

        except Exception as e:
            return format_response(False, str(e), error_code=-500, http_status=500)
    @http.route(
        ['/sales_rep_manager/<string:api_version>/profile'],
        type='http', auth='none', methods=['GET', 'OPTIONS'], csrf=False, cors='*'
    )
    @jwt_required()
    def get_sales_rep_profile(self, **kwargs):
        if request.httprequest.method == 'OPTIONS':
            return json_response({"ok": True}, status=200)

        try:
            env = kwargs['_jwt_env']
            user = env.user

            Profile = env['sales.rep.profile'].sudo()
            profile = Profile.search([('user_id', '=', user.id)], limit=1)

            if not profile:
                return format_response(
                    False,
                    "Sales representative profile not found",
                    error_code=404,
                    http_status=404
                )

            # cash journals mapping
            journals = []
            for line in profile.journal_map_ids:
                journal = line.journal_id
                currency = line.currency_id
                journals.append({
                    "journal_id": journal.id,
                    "journal_name": journal.display_name,
                    "currency_id": currency.id if currency else None,
                    "currency_name": currency.name if currency else None,
                    "currency_symbol": currency.symbol if currency else None,
                })

            # ---------------------------------------------------------
            # بداية الإضافة: جلب آخر فاتورة وآخر مرتجع كما في Login
            # ---------------------------------------------------------
            AccountMove = env['account.move'].sudo()

            # 1. جلب آخر فاتورة نظامية
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

            # ---------------------------------------------------------
            # نهاية الإضافة
            # ---------------------------------------------------------

            # (الجديد) جلب إعدادات التقريب الخاصة بـ NAD Cash Rounding
            rounding_val = 0.0
            rounding_rec = env['account.cash.rounding'].sudo().search([
                ('name', '=', 'NAD Cash Rounding')
            ], limit=1)

            if rounding_rec:
                rounding_val = rounding_rec.rounding
            company = profile.company_id
            currency = company.currency_id if company else None
            data = {
                "id": profile.id,
                "sequence": noneify(profile.sequence),
                "name": noneify(profile.name),

                # تمت إضافة الحقول الجديدة هنا
                "allowed_distance_m": noneify(profile.allowed_distance_m),
                "last_local_invoice": last_local_invoice,
                "last_local_return_invoice": last_local_return_invoice,

                # user
                "user": {
                    "id": profile.user_id.id,
                    "name": profile.user_id.name,
                    "login": profile.user_id.login,
                },

                # company

                "company": {
                    "id": safe(company.id),
                    "name": safe(company.name),

                    "currency": {
                        "id": safe(currency.id),
                        "name": safe(currency.name),
                        "symbol": safe(currency.symbol),
                    } if currency else None,

                    "mobile": safe(company.mobile),
                    "phone": safe(company.phone),
                    "email": safe(company.email),
                    "website": safe(company.website),
                    "country": safe(company.country_id.name),
                    "address": safe(company.street),
                    "city": safe(company.city),
                    "vat": safe(company.vat) or "",
                    "company_registry": safe(company.company_registry),
                },

                # configuration
                "sales_team_type": profile.sales_team_type,
                "allow_usd_payment": profile.allow_usd_payment,
                "attachment_mandatory": profile.attachment_mandatory,
                "nad_rounding_value": rounding_val,

                # route & location
                "route": {
                    "id": profile.route_id.id if profile.route_id else None,
                    "name": profile.route_id.display_name if profile.route_id else None,
                },
                "location": {
                    "id": profile.location_id.id if profile.location_id else None,
                    "name": profile.location_id.display_name if profile.location_id else None,
                },

                # operation type
                "operation_type": {
                    "id": profile.operation_type_id.id if profile.operation_type_id else None,
                    "name": profile.operation_type_id.display_name if profile.operation_type_id else None,
                },

                # cash journals per currency
                "cash_journals": journals,
            }

            return format_response(
                True,
                "Sales representative profile",
                data,
                http_status=200
            )

        except Exception as e:
            _logger.exception("Error fetching sales rep profile")
            return format_response(
                False,
                f"Internal error: {str(e)}",
                error_code=-500,
                http_status=500
            )

    @http.route(
        ['/sales_rep_manager/<string:api_version>/app/version'],
        type='http', auth='none', methods=['GET', 'OPTIONS'], csrf=False, cors='*'
    )
    @jwt_required()
    def get_app_version(self, **kwargs):
        if request.httprequest.method == 'OPTIONS':
            return json_response({"ok": True}, status=200)

        try:
            data = {
                "version": "1.0.2",
                "download_url": "http://nad.s-apps.online:11111/down/Motahdon-Test.apk",
            }

            return format_response(
                True,
                "App version info",
                data,
                http_status=200
            )

        except Exception as e:
            _logger.exception("Error fetching app version info")
            return format_response(
                False,
                f"Internal error: {str(e)}",
                error_code=-500,
                http_status=500
            )

    @http.route([
        '/sales_rep_manager/<string:api_version>/areas',
        '/sales_rep_manager/<string:api_version>/get_areas',
    ], type='http', auth='none', methods=['GET', 'OPTIONS'], csrf=False, cors="*")
    @jwt_required()
    def get_areas(self, **kwargs):
        if request.httprequest.method == 'OPTIONS':
            return request.make_response(
                headers=[('Content-Type', 'application/json')],
                data=json.dumps({"ok": True}),
                status=200
            )

        try:
            env = kwargs["_jwt_env"]
            current_user = env['res.users'].browse(kwargs["_jwt_user_id"])

            # ======= جلب معرّف المحافظة من الـ query params =======
            governorate_id = request.params.get('governorate_id')

            # ======= بناء الدومين =======
            domain = []
            if governorate_id:
                try:
                    governorate_id = int(governorate_id)
                    domain.append(('state_id', '=', governorate_id))
                except (ValueError, TypeError):
                    return format_response(
                        False,
                        "Invalid governorate_id parameter, must be an integer",
                        data={"total": 0, "areas": []},
                        http_status=400
                    )

            # ======= جلب المناطق (المدن) =======
            CityModel = env['res.city'].sudo()
            cities = CityModel.search(domain, order='name asc')

            if not cities:
                return format_response(
                    False,
                    "No areas found" + (f" for governorate_id={governorate_id}" if governorate_id else ""),
                    data={"total": 0, "areas": []}
                )

            # ======= بناء قائمة المناطق =======
            area_list = []
            for city in cities:
                area_list.append({
                    "id": city.id,
                    "name": noneify(city.name),
                    "zipcode": noneify(getattr(city, 'zipcode', None)),
                    "governorate": ({
                                        "id": city.state_id.id,
                                        "name": noneify(city.state_id.name),
                                        "code": noneify(city.state_id.code),
                                    } if city.state_id else None),
                    "country": ({
                                    "id": city.country_id.id,
                                    "name": noneify(city.country_id.name),
                                } if city.country_id else None),
                })

            return format_response(True, "Areas fetched successfully", {
                "total": len(cities),
                "areas": area_list
            }, http_status=200)

        except Exception as e:
            _logger.exception("Error fetching areas")
            return format_response(
                False,
                f"Internal error: {str(e)}",
                error_code=-500,
                http_status=500
            )