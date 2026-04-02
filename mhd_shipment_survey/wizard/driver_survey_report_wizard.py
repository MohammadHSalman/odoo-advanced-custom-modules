# wizard/driver_survey_report_wizard.py
from odoo import api, fields, models, _
from odoo.exceptions import ValidationError

class DriverSurveyReportWizard(models.TransientModel):
    _name = "driver.survey.report.wizard"
    _description = "Driver Survey Yes/No Report"

    driver_id = fields.Many2one(
        "res.partner", string="Driver", required=True,
        domain=[("is_company", "=", False)]
    )
    question_id = fields.Many2one("survey.question", string="Question (optional)")
    date_from = fields.Datetime(string="From")
    date_to = fields.Datetime(string="To")

    yes_count = fields.Integer(string="Yes", compute="_compute_stats", store=False)
    no_count = fields.Integer(string="No", compute="_compute_stats", store=False)
    total_count = fields.Integer(string="Total", compute="_compute_stats", store=False)
    pct_yes = fields.Float(string="% Yes", compute="_compute_stats", store=False, digits=(16,2))
    pct_no = fields.Float(string="% No", compute="_compute_stats", store=False, digits=(16,2))

    def _domain_lines(self):
        self.ensure_one()
        dom = [("driver_id", "=", self.driver_id.id)]
        if self.question_id:
            dom.append(("question_id", "=", self.question_id.id))
        if self.date_from:
            dom.append(("completed_at", ">=", self.date_from))
        if self.date_to:
            dom.append(("completed_at", "<=", self.date_to))
        return dom

    @api.depends('driver_id', 'question_id', 'date_from', 'date_to')
    def _compute_stats(self):
        Line = self.env["driver.survey.line"].sudo()
        for wiz in self:
            if not wiz.driver_id:
                wiz.yes_count = wiz.no_count = wiz.total_count = 0
                wiz.pct_yes = wiz.pct_no = 0.0
                continue
            dom = wiz._domain_lines()
            yes_cnt = Line.search_count(dom + [("answer_yesno", "=", "yes")])
            no_cnt  = Line.search_count(dom + [("answer_yesno", "=", "no")])
            total = yes_cnt + no_cnt
            wiz.yes_count = yes_cnt
            wiz.no_count = no_cnt
            wiz.total_count = total
            wiz.pct_yes = (yes_cnt * 100.0 / total) if total else 0.0
            wiz.pct_no  = (no_cnt  * 100.0 / total) if total else 0.0

    def action_open_records(self):
        """فتح السجلات التفصيلية بنفس أسلوب العرض (tree/graph)"""
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Driver Survey (Filtered)"),
            "res_model": "driver.survey.line",
            "view_mode": "tree,graph",
            "domain": self._domain_lines(),
            "target": "current",
        }

    def action_open_pie(self):
        """فتح الجراف الدائري (نسب نعم/لا)"""
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Driver Survey (Yes/No)"),
            "res_model": "driver.survey.line",
            "view_mode": "graph,tree",
            "domain": self._domain_lines(),
            "context": {"graph_view": "pie"},
            "target": "current",
        }
