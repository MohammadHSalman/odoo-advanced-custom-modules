# -*- coding: utf-8 -*-
# from odoo import http


# class SaharaPlanet(http.Controller):
#     @http.route('/sahara_planet/sahara_planet', auth='public')
#     def index(self, **kw):
#         return "Hello, world"

#     @http.route('/sahara_planet/sahara_planet/objects', auth='public')
#     def list(self, **kw):
#         return http.request.render('sahara_planet.listing', {
#             'root': '/sahara_planet/sahara_planet',
#             'objects': http.request.env['sahara_planet.sahara_planet'].search([]),
#         })

#     @http.route('/sahara_planet/sahara_planet/objects/<model("sahara_planet.sahara_planet"):obj>', auth='public')
#     def object(self, obj, **kw):
#         return http.request.render('sahara_planet.object', {
#             'object': obj
#         })
