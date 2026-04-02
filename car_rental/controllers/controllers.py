# -*- coding: utf-8 -*-
# from odoo import http


# class CarRental(http.Controller):
#     @http.route('/car_rental/car_rental', auth='public')
#     def index(self, **kw):
#         return "Hello, world"

#     @http.route('/car_rental/car_rental/objects', auth='public')
#     def list(self, **kw):
#         return http.request.render('car_rental.listing', {
#             'root': '/car_rental/car_rental',
#             'objects': http.request.env['car_rental.car_rental'].search([]),
#         })

#     @http.route('/car_rental/car_rental/objects/<model("car_rental.car_rental"):obj>', auth='public')
#     def object(self, obj, **kw):
#         return http.request.render('car_rental.object', {
#             'object': obj
#         })
