from odoo import models, fields, api


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    pos_iface_printbill = fields.Boolean(store=True, readonly=False, default=False)

    @api.depends('pos_module_pos_restaurant', 'pos_config_id')
    def _compute_pos_module_pos_restaurant(self):
        for res_config in self:
            if not res_config.pos_module_pos_restaurant:
                res_config.update({
                    'pos_iface_orderline_notes': False,
                    'pos_iface_splitbill': False,
                })
            else:
                res_config.update({
                    'pos_iface_orderline_notes': res_config.pos_config_id.iface_orderline_notes,
                    'pos_iface_splitbill': res_config.pos_config_id.iface_splitbill,
                })
