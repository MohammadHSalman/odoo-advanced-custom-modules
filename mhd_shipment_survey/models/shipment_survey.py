# -*- coding: utf-8 -*-
from odoo import api, fields, models, _, tools
from odoo.exceptions import ValidationError
import re
import logging

_logger = logging.getLogger(__name__)

# =========================
# 0) Survey User Input Line (normalize yes/no)
# =========================
class SurveyUserInputLine(models.Model):
    _inherit = "survey.user_input.line"

    answer_yesno = fields.Selection(
        [("yes", "Yes"), ("no", "No"), ("other", "Other/Skipped")],
        string="Yes/No (Normalized)",
        compute="_compute_answer_yesno",
        store=True,
        index=True,
    )

    @api.depends('display_name')  # <-- أضِف هذه
    def _compute_answer_yesno(self):
        YES = {"yes", "نعم", "اي", "ايه", "ايوا", "ايوه", "yaa", "ok"}
        NO  = {"no", "لا", "لاء", "nope"}
        for line in self:
            txt = (line.display_name or "").strip().lower()
            if txt in YES:
                line.answer_yesno = "yes"
            elif txt in NO:
                line.answer_yesno = "no"
            else:
                line.answer_yesno = "other"


# =========================
# 1) Shipment Survey History
# =========================
class ShipmentSurveyHistory(models.Model):
    _name = "shipment.survey.history"
    _description = "Shipment Survey History"
    _order = "create_date desc"
    _rec_name = "shipment_id"

    shipment_id = fields.Many2one("shipment.order", required=True, index=True, ondelete="cascade")

    # تم استبدال partner_id بـ first_name (related من الشحنة)
    first_name = fields.Char(related="shipment_id.first_name", string="First Name", readonly=True)

    phone = fields.Char()
    channel = fields.Selection([("whatsapp", "WhatsApp")], default="whatsapp", required=True)
    template_id = fields.Many2one("odx.whatsapp.template", string="WhatsApp Template")
    url = fields.Char()
    status = fields.Selection(
        [("sent", "Sent"), ("failed", "Failed"), ("completed", "Completed")],
        default="sent",
        required=True
    )
    message = fields.Text()
    message_sid = fields.Char()
    error = fields.Text()
    answer_id = fields.Many2one("survey.user_input", string="Survey Answer")
    sent_at = fields.Datetime(default=fields.Datetime.now)
    completed_at = fields.Datetime()

    # حفظ السائق الذي كانت عليه الشحنة لحظة الإرسال/الاكتمال
    delivery_boy_partner_id = fields.Many2one(
        "res.partner",
        string="Driver",
        help="The delivery boy linked to the shipment at the time of sending/completion."
    )

    # عرض سطور الإجابات المرتبطة بهذه الإجابة
    answer_line_ids = fields.One2many(
        comodel_name="survey.user_input.line",
        inverse_name="user_input_id",
        string="Answers",
        related="answer_id.user_input_line_ids",
        readonly=True,
    )


# =========================
# 2) Survey User Input (link to shipment + capture completion)
# =========================
class SurveyUserInput(models.Model):
    _inherit = "survey.user_input"

    # ربط الإجابة بالشحنة
    shipment_id = fields.Many2one("shipment.order", index=True, ondelete="cascade")

    def write(self, vals):
        """عند انتقال حالة الإجابة إلى 'done' (أو 'completed' لو لديك تخصيص)،
        حدّث سجلات الـ History المرتبطة لتصبح 'completed' واحفظ السائق."""
        res = super().write(vals)

        state_now = vals.get("state")
        if state_now in ("done", "completed"):
            History = self.env["shipment.survey.history"].sudo()
            now_dt = fields.Datetime.now()

            for ans in self:
                # استحضار السائق من الشحنة إن وُجد
                driver_id = False
                if ans.shipment_id:
                    driver = getattr(ans.shipment_id, "delivery_boy_partner_id", False)
                    driver_id = driver.id if driver else False

                histories = History.search([("answer_id", "=", ans.id)])
                if histories:
                    histories.write({
                        "status": "completed",
                        "completed_at": now_dt,
                        "delivery_boy_partner_id": driver_id,
                    })
                else:
                    History.create({
                        "shipment_id": ans.shipment_id.id if ans.shipment_id else False,
                        "phone": (ans.shipment_id.mobile or ans.shipment_id.phone) if ans.shipment_id else False,
                        "channel": "whatsapp",
                        "template_id": False,
                        "url": False,
                        "status": "completed",
                        "message": _("Survey completed by customer."),
                        "message_sid": False,
                        "error": False,
                        "answer_id": ans.id,
                        "completed_at": now_dt,
                        "delivery_boy_partner_id": driver_id,
                    })

                # تدوينة في الشحنة (اختياري)
                if ans.shipment_id:
                    driver_name = "-"
                    if driver_id:
                        driver_name = ans.shipment_id.delivery_boy_partner_id.display_name
                    ans.shipment_id.message_post(
                        body=_("Survey marked as <b>Completed</b>. Driver: %s") % driver_name
                    )

        return res


# =========================
# 3) Shipment Order (defaults, sending, history, smart button)
# =========================
class ShipmentOrder(models.Model):
    _inherit = "shipment.order"

    # -----------------------------
    # جلب الديفولت من الكونّكتور
    # -----------------------------
    def _get_default_whatsapp_template_id(self):
        connector = self.env["odx.freshchat.connector"].sudo().search([("active", "=", True)], limit=1)
        return connector.whatsapp_template_id.id if connector and connector.whatsapp_template_id else False

    def _get_default_survey_id(self):
        connector = self.env["odx.freshchat.connector"].sudo().search([("active", "=", True)], limit=1)
        return connector.survey_id.id if connector and connector.survey_id else False

    # -----------------------------
    # حقول الاستبيان على الشحنة
    # -----------------------------
    survey_id = fields.Many2one("survey.survey", string="Survey", readonly=False)
    survey_sent = fields.Boolean(
        string="Survey Sent",
        compute="_compute_survey_sent",
        store=True,
        readonly=True,
    )

    @api.depends("survey_history_ids.status")
    def _compute_survey_sent(self):
        for rec in self:
            # يتحول True إذا وُجد أي سجل sent أو completed
            rec.survey_sent = any(
                h.status in ("sent", "completed") for h in rec.survey_history_ids
            )
    survey_answer_id = fields.Many2one("survey.user_input", string="Survey Answer", readonly=True)
    survey_url = fields.Char(string="Survey URL")
    whatsapp_template_id = fields.Many2one(
        "odx.whatsapp.template",
        string="WhatsApp Template (Survey)",
        help="Template used to send the survey link to the customer.",
        readonly=False,
    )

    # تاريخ الاستبيانات (One2many)
    survey_history_ids = fields.One2many("shipment.survey.history", "shipment_id", string="Survey History")

    # عدّاد + زر ذكي
    survey_history_count = fields.Integer(string="Surveys", compute="_compute_survey_history_count", store=False)

    def _compute_survey_history_count(self):
        for rec in self:
            rec.survey_history_count = len(rec.survey_history_ids)

    def action_open_survey_history(self):
        self.ensure_one()
        return {
            "name": _("Survey History"),
            "type": "ir.actions.act_window",
            "res_model": "shipment.survey.history",
            "view_mode": "tree,form",
            "domain": [("shipment_id", "=", self.id)],
            "context": {"default_shipment_id": self.id},
            "target": "current",
        }

    # -----------------------------
    # Helpers
    # -----------------------------
    def _absolute_url(self, relative):
        base = self.env["ir.config_parameter"].sudo().get_param("web.base.url", "")
        if relative and not relative.startswith(("http://", "https://")):
            return (base.rstrip("/") + "/" + relative.lstrip("/")) if base else relative
        return relative

    def _already_pushed_survey(self):
        """Return True if this shipment already has a survey push (sent/completed)."""
        self.ensure_one()
        if self.survey_sent:
            return True
        History = self.env["shipment.survey.history"].sudo()
        # نعتبر أي sent/completed سابق قفلاً تاماً ضد أي إرسال لاحق أو failed لاحق
        return bool(History.search_count([
            ('shipment_id', '=', self.id),
            ('status', 'in', ['sent', 'completed'])
        ]))

    # مانع إنشاء failed/double history
    def _create_history_once(self, vals):
        """Create history row if a similar one doesn't already exist.
        كما يمنع failed إن كان هناك sent/completed سابقاً لهذه الشحنة."""
        History = self.env["shipment.survey.history"].sudo()

        # لا تُسجّل FAILED إذا كان لدينا SENT/COMPLETED سابق
        if vals.get('status') == 'failed' and vals.get('shipment_id'):
            has_ok = History.search_count([
                ('shipment_id', '=', vals['shipment_id']),
                ('status', 'in', ['sent', 'completed'])
            ])
            if has_ok:
                _logger.warning("Skip FAILED history because SENT/COMPLETED exists | shipment_id=%s", vals['shipment_id'])
                return False

        # de-duplication أساسي
        dom = [('shipment_id', '=', vals.get('shipment_id'))]
        if vals.get('status'):
            dom.append(('status', '=', vals['status']))
        if vals.get('answer_id'):
            dom.append(('answer_id', '=', vals['answer_id']))
        if vals.get('message_sid'):
            dom.append(('message_sid', '=', vals['message_sid']))
        else:
            if vals.get('phone'):
                dom.append(('phone', '=', vals['phone']))
            if vals.get('url'):
                dom.append(('url', '=', vals['url']))

        if History.search_count(dom):
            _logger.warning("Skip duplicate history: dom=%s", dom)
            return False

        History.create(vals)
        return True

    # -----------------------------
    # create: ملء الديفولت من الكونّكتور
    # -----------------------------
    @api.model
    def create(self, vals):
        if not vals.get("whatsapp_template_id"):
            t_id = self._get_default_whatsapp_template_id()
            if t_id:
                vals["whatsapp_template_id"] = t_id
        if not vals.get("survey_id"):
            s_id = self._get_default_survey_id()
            if s_id:
                vals["survey_id"] = s_id
        return super().create(vals)

    # -----------------------------
    # write: عند التسليم/الإنهاء أرسل الاستبيان وسجّل التاريخ
    # -----------------------------
    def write(self, vals):
        _logger.info("SHIPMENT.write START | ids=%s | vals=%s", self.ids, vals)

        state_will_change = "state" in vals
        new_state = (vals.get("state") or "").lower() if state_will_change else False
        _logger.debug("SHIPMENT.write | state_will_change=%s | new_state=%s", state_will_change, new_state)

        # تصحيح ذاتي للسجلات القديمة (يملأ الديفولت من الكونّكتور)
        for rec in self:
            try:
                to_fix = {}
                if not (vals.get("whatsapp_template_id") or rec.whatsapp_template_id):
                    t_id = rec._get_default_whatsapp_template_id()
                    if t_id:
                        to_fix["whatsapp_template_id"] = t_id
                if not (vals.get("survey_id") or rec.survey_id):
                    s_id = rec._get_default_survey_id()
                    if s_id:
                        to_fix["survey_id"] = s_id
                if to_fix:
                    _logger.info("SHIPMENT[%s] autofix defaults -> %s", rec.id, to_fix)
                    super(ShipmentOrder, rec).write(to_fix)
            except Exception as e:
                _logger.exception("SHIPMENT[%s] autofix defaults FAILED: %s", rec.id, e)

        res = super().write(vals)
        _logger.debug("SHIPMENT.write super done | ids=%s", self.ids)

        # عند الوصول إلى حالة التسليم/الإنهاء، حضّر وأرسل رابط الاستبيان عبر الواتساب
        if state_will_change and new_state in ("delivered", "done"):
            _logger.info("SHIPMENT.write POST-STATE | triggering survey send | ids=%s", self.ids)
            for rec in self:
                _logger.info("SURVEY FLOW START | shipment_id=%s | partner=%s",
                             rec.id, rec.partner_id and rec.partner_id.display_name)
                try:
                    # ===== منع التكرار (حارس مبكر) =====
                    if rec._already_pushed_survey():
                        _logger.info("SKIP survey push (already sent/completed) | shipment_id=%s", rec.id)
                        continue

                    connector = rec.env["odx.freshchat.connector"].sudo().search([("active", "=", True)], limit=1)
                    _logger.debug("CONNECTOR | found=%s", bool(connector))
                    survey = rec.survey_id or (connector.survey_id if connector else False)
                    wtmpl = rec.whatsapp_template_id or (connector.whatsapp_template_id if connector else False)
                    _logger.info("SURVEY/TEMPLATE | survey_id=%s | wtmpl_id=%s",
                                 getattr(survey, "id", None), getattr(wtmpl, "id", None))

                    if not survey or not wtmpl:
                        _logger.error("MISSING survey/template | shipment_id=%s", rec.id)
                        raise ValidationError(_("Survey and WhatsApp template must be set on the active Freshchat connector (or on the shipment)."))

                    # --- إنشاء/استرجاع إجابة الاستبيان + بناء الرابط ---
                    UserInput = rec.env["survey.user_input"].sudo()
                    partner = rec.partner_id
                    answer = UserInput.search(
                        [("survey_id", "=", survey.id), ("shipment_id", "=", rec.id)],
                        limit=1, order="id desc"
                    )
                    _logger.debug("ANSWER search | found=%s | id=%s", bool(answer), getattr(answer, "id", None))

                    # اختيار user آمن
                    uid = rec.env.uid or False
                    user_rec = rec.env["res.users"].browse(uid) if uid else rec.env["res.users"]
                    public_user = rec.env.ref("base.public_user", raise_if_not_found=False)
                    is_valid_user = bool(uid) and user_rec.exists() and (not public_user or user_rec.id != public_user.id)
                    safe_user = user_rec if is_valid_user else False

                    if not answer:
                        extra = {"shipment_id": rec.id}
                        if partner:
                            answer = survey.sudo()._create_answer(
                                user=safe_user,
                                partner=partner,
                                email=partner.email or False,
                                test_entry=False,
                                check_attempts=True,
                                **extra
                            )
                            _logger.info("ANSWER created WITH partner | answer_id=%s", answer.id)
                        else:
                            answer = survey.sudo()._create_answer(
                                user=safe_user,
                                email=False,
                                test_entry=False,
                                check_attempts=True,
                                **extra
                            )
                            _logger.info("ANSWER created WITHOUT partner | answer_id=%s", answer.id)

                    if answer:
                        rel = "/survey/%s/%s" % (answer.survey_id.access_token, answer.access_token)
                        abs_url = rec._absolute_url(rel)
                        _logger.debug("SURVEY URL | rel=%s | abs=%s", rel, abs_url)
                        rec.sudo().write({"survey_answer_id": answer.id, "survey_url": abs_url})
                        _logger.info("SURVEY fields set on shipment | survey_answer_id=%s", answer.id)

                        # ===== منع التكرار بعد توفر answer/URL =====
                        if rec._already_pushed_survey():
                            _logger.info(
                                "SKIP survey push (history says sent/completed) | shipment_id=%s | answer_id=%s",
                                rec.id, answer.id
                            )
                            continue

                    # --- نوع الميديا من القالب ---
                    media_url = False
                    mt = wtmpl.message_type
                    if mt == "image":
                        media_url = wtmpl.image_url
                    elif mt == "video":
                        media_url = wtmpl.video_url
                    elif mt == "document":
                        media_url = wtmpl.document_url
                    _logger.debug("MEDIA | type=%s | url=%s", mt, media_url)

                    # --- تهيئة رقم الهاتف ---
                    raw_phone = rec.mobile or rec.phone or False
                    _logger.debug("PHONE raw | %s", raw_phone)

                    def _normalize_phone_for_shipment(raw, shipment_country, company):
                        if not raw:
                            return (False, "Missing phone on shipment (mobile/phone)")

                        s = str(raw).strip()

                        # 1) لو الرقم بصيغة دولية جاهزة (+...)
                        if s.startswith("+"):
                            digits = re.sub(r"\D", "", s)
                            if not digits:
                                return (False, "Phone has no digits")
                            # + مع الأرقام فقط
                            return ("+" + digits, None)

                        # 2) إزالة كل ما ليس رقم
                        digits = re.sub(r"\D", "", s)
                        if not digits:
                            return (False, "Phone has no digits")

                        # 3) 00.. → دولي
                        if digits.startswith("00"):
                            digits = digits[2:]

                        # 4) تحديد كود البلد
                        phone_code = False
                        if shipment_country and getattr(shipment_country, "phone_code", False):
                            phone_code = str(shipment_country.phone_code).lstrip("+").lstrip("0")
                        elif company and company.country_id and getattr(company.country_id, "phone_code", False):
                            phone_code = str(company.country_id.phone_code).lstrip("+").lstrip("0")
                        if not phone_code:
                            return (False, "Missing country phone code on shipment/company")

                        # 5) إن كانت الأرقام تبدأ أصلاً بكود البلد → لا تضف الكود مرة أخرى
                        if digits.startswith(phone_code):
                            e164_no_plus = digits
                        else:
                            # شِل الصفر الافتتاحي الوطني فقط في الحالة المحلية
                            if digits.startswith("0"):
                                digits = digits.lstrip("0")
                                if not digits:
                                    return (False, "Empty after stripping leading zeros")
                            e164_no_plus = phone_code + digits

                        if len(e164_no_plus) < 10:
                            return (False, "Phone too short after normalization")

                        return ("+" + e164_no_plus, None)

                    e164_phone, phone_err = _normalize_phone_for_shipment(
                        raw_phone, rec.country_id, (rec.company_id or rec.env.company)
                    )
                    _logger.info("PHONE normalized | e164=%s | err=%s", e164_phone, phone_err)

                    # حضّر السائق ليُحفظ في History
                    driver = getattr(rec, "delivery_boy_partner_id", False)
                    driver_id = driver.id if driver else False
                    _logger.debug("DRIVER | driver_id=%s", driver_id)

                    # ===== حالات فشل مبكر — ممنوعة إن كان هناك sent/completed سابق =====
                    if not e164_phone:
                        if rec._already_pushed_survey():
                            _logger.info("Skip FAILED phone because SENT exists | shipment_id=%s", rec.id)
                            continue
                        self._create_history_once({
                            "shipment_id": rec.id,
                            "phone": raw_phone or False,
                            "template_id": wtmpl.id,
                            "url": rec.survey_url or False,
                            "status": "failed",
                            "message": _("WhatsApp survey push FAILED."),
                            "error": phone_err or _("Invalid phone"),
                            "answer_id": answer.id if answer else False,
                            "delivery_boy_partner_id": driver_id,
                        })
                        rec.message_post(body=_("Survey WhatsApp sending error: %s (shipment phone: %s)")
                                              % (phone_err or "-", raw_phone or "-"))
                        continue

                    if not rec.survey_url:
                        if rec._already_pushed_survey():
                            _logger.info("Skip FAILED url because SENT exists | shipment_id=%s", rec.id)
                            continue
                        self._create_history_once({
                            "shipment_id": rec.id,
                            "phone": e164_phone,
                            "template_id": wtmpl.id,
                            "url": rec.survey_url or False,
                            "status": "failed",
                            "message": _("WhatsApp survey push FAILED."),
                            "error": _("Missing survey_url value for template placeholders"),
                            "answer_id": answer.id if answer else False,
                            "delivery_boy_partner_id": driver_id,
                        })
                        rec.message_post(body=_("Survey WhatsApp sending error: Missing survey_url placeholder value"))
                        continue

                    connector = connector or rec.env["odx.freshchat.connector"].sudo().search([("active", "=", True)], limit=1)
                    _logger.debug("CONNECTOR (recheck) | exists=%s", bool(connector))
                    if not connector:
                        _logger.error("NO CONNECTOR CONFIGURED | shipment_id=%s", rec.id)
                        rec.message_post(body=_("No Freshchat connector configured. Cannot send survey WhatsApp."))
                        continue

                    # ===== الإرسال =====
                    try:
                        _logger.info("SENDING WHATSAPP | shipment_id=%s | to=%s | template=%s", rec.id, e164_phone, wtmpl.id)
                        request_id = connector.send_whatsapp_message_into_shipper(rec, connector, wtmpl, media_url)
                        request_text = request_id if isinstance(request_id, str) else str(request_id or "")
                        sent_ok = bool(request_text) and ("failed" not in request_text.lower())
                        _logger.info("WHATSAPP RESPONSE | sent_ok=%s | request_text=%s", sent_ok, request_text)

                        # History sent/failed — باستخدام de-dup + منع failed بعد sent
                        self._create_history_once({
                            "shipment_id": rec.id,
                            "phone": e164_phone,
                            "template_id": wtmpl.id,
                            "url": rec.survey_url or False,
                            "status": "sent" if sent_ok else "failed",
                            "message_sid": request_text if request_text else False,
                            "message": _("WhatsApp survey push %s.") % ("OK" if sent_ok else "FAILED"),
                            "error": False if sent_ok else request_text,
                            "answer_id": answer.id if answer else False,
                            "delivery_boy_partner_id": driver_id,
                        })

                        rec.message_post(body=_("Survey WhatsApp request: %s<br/>URL: %s<br/>To: %s")
                                              % (request_text or "-", rec.survey_url or "-", e164_phone))

                        if sent_ok:
                            # ضع العلم و اخرج فوراً — لن تُسجل أي failed تالٍ
                            # rec.sudo().write({"survey_sent": True})
                            _logger.info("SURVEY SENT FLAG set True | shipment_id=%s", rec.id)
                            continue

                    except Exception as e:
                        _logger.exception("WHATSAPP SENDING EXCEPTION | shipment_id=%s | err=%s", rec.id, e)
                        # لا تسجل failed إذا كان هناك sent/completed سابق
                        if not rec._already_pushed_survey():
                            self._create_history_once({
                                "shipment_id": rec.id,
                                "phone": e164_phone,
                                "template_id": wtmpl.id,
                                "url": rec.survey_url or False,
                                "status": "failed",
                                "message": _("WhatsApp survey push FAILED."),
                                "error": str(e),
                                "answer_id": answer.id if answer else False,
                                "delivery_boy_partner_id": driver_id,
                            })
                        rec.message_post(body=_("Survey WhatsApp sending exception: %s") % str(e))

                except Exception as e:
                    _logger.exception("SURVEY FLOW FAILED | shipment_id=%s | err=%s", rec.id, e)

        _logger.info("SHIPMENT.write END | ids=%s", self.ids)
        return res


# =========================
# 4) Driver Survey Line (SQL View)
# =========================
class DriverSurveyLine(models.Model):
    _name = "driver.survey.line"
    _description = "Driver Survey Lines (Yes/No) for Graph"
    _auto = False
    _rec_name = "shipment_id"

    driver_id = fields.Many2one("res.partner", string="Driver", index=True)
    shipment_id = fields.Many2one("shipment.order", string="Shipment", index=True)
    partner_id = fields.Many2one("res.partner", string="Customer", index=True)
    question_id = fields.Many2one("survey.question", string="Question", index=True)
    answer_yesno = fields.Selection([("yes","Yes"),("no","No")], string="Answer (Yes/No)", index=True)
    completed_at = fields.Datetime(string="Completed At", index=True)

    def init(self):
        tools.drop_view_if_exists(self._cr, 'driver_survey_line')
        self._cr.execute("""
            CREATE VIEW driver_survey_line AS
            WITH hist AS (
                SELECT
                    h.answer_id,
                    h.shipment_id,
                    h.delivery_boy_partner_id AS driver_id,
                    MAX(h.completed_at)      AS completed_at
                FROM shipment_survey_history h
                WHERE h.status = 'completed' AND h.answer_id IS NOT NULL
                GROUP BY h.answer_id, h.shipment_id, h.delivery_boy_partner_id
            )
            SELECT
                -- id تركيب ثابت لتجنّب التعارض
                (l.id * 100000 + COALESCE(hist.driver_id,0))::bigint AS id,
                hist.driver_id             AS driver_id,
                hist.shipment_id           AS shipment_id,
                so.partner_id              AS partner_id,
                l.question_id              AS question_id,
                CASE WHEN l.answer_yesno IN ('yes','no') THEN l.answer_yesno ELSE NULL END AS answer_yesno,
                hist.completed_at          AS completed_at
            FROM survey_user_input_line l
            JOIN hist
              ON hist.answer_id = l.user_input_id
            LEFT JOIN shipment_order so
              ON so.id = hist.shipment_id
            WHERE l.answer_yesno IN ('yes','no')
        """)
