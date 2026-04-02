# -*- coding: utf-8 -*-
# from odoo import http


# class PassportBarcode(http.Controller):
#     @http.route('/passport_barcode/passport_barcode', auth='public')
#     def index(self, **kw):
#         return "Hello, world"

#     @http.route('/passport_barcode/passport_barcode/objects', auth='public')
#     def list(self, **kw):
#         return http.request.render('passport_barcode.listing', {
#             'root': '/passport_barcode/passport_barcode',
#             'objects': http.request.env['passport_barcode.passport_barcode'].search([]),
#         })

#     @http.route('/passport_barcode/passport_barcode/objects/<model("passport_barcode.passport_barcode"):obj>', auth='public')
#     def object(self, obj, **kw):
#         return http.request.render('passport_barcode.object', {
#             'object': obj
#         })
