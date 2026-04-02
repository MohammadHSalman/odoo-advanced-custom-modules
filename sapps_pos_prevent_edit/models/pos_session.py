# -*- coding: utf-8 -*-

from odoo import models


class PosSession(models.Model):

    _inherit = 'pos.session'

    def _loader_params_res_users(self):
        result = super()._loader_params_res_users()
        result['search_params']['fields'].extend(
            ['disable_cancellation'])
        return result


