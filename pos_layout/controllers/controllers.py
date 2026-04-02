# -*- coding: utf-8 -*-
# from odoo import http


# class PosSahara(http.Controller):
#     @http.route('/pos_sahara/pos_sahara', auth='public')
#     def index(self, **kw):
#         return "Hello, world"

#     @http.route('/pos_sahara/pos_sahara/objects', auth='public')
#     def list(self, **kw):
#         return http.request.render('pos_sahara.listing', {
#             'root': '/pos_sahara/pos_sahara',
#             'objects': http.request.env['pos_sahara.pos_sahara'].search([]),
#         })

#     @http.route('/pos_sahara/pos_sahara/objects/<model("pos_sahara.pos_sahara"):obj>', auth='public')
#     def object(self, obj, **kw):
#         return http.request.render('pos_sahara.object', {
#             'object': obj
#         })
