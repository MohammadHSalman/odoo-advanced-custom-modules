# -*- coding: utf-8 -*-
# from odoo import http


# class SaharaInvoiceTabby(http.Controller):
#     @http.route('/sahara_invoice_tabby/sahara_invoice_tabby', auth='public')
#     def index(self, **kw):
#         return "Hello, world"

#     @http.route('/sahara_invoice_tabby/sahara_invoice_tabby/objects', auth='public')
#     def list(self, **kw):
#         return http.request.render('sahara_invoice_tabby.listing', {
#             'root': '/sahara_invoice_tabby/sahara_invoice_tabby',
#             'objects': http.request.env['sahara_invoice_tabby.sahara_invoice_tabby'].search([]),
#         })

#     @http.route('/sahara_invoice_tabby/sahara_invoice_tabby/objects/<model("sahara_invoice_tabby.sahara_invoice_tabby"):obj>', auth='public')
#     def object(self, obj, **kw):
#         return http.request.render('sahara_invoice_tabby.object', {
#             'object': obj
#         })
