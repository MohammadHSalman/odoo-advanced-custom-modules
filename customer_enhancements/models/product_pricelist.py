from odoo import models, fields, api, _

try:
    from markupsafe import Markup
except ImportError:
    def Markup(html_string):
        return html_string


class Pricelist(models.Model):
    _inherit = "product.pricelist"

    item_ids = fields.One2many(tracking=False)


class PricelistItem(models.Model):
    _inherit = "product.pricelist.item"

    def write(self, vals):
        field_labels = {
            'min_quantity': 'Min Qty',
            'fixed_price': 'Fixed Price',
            'percent_price': 'Percentage',
            'date_start': 'Start Date',
            'date_end': 'End Date',
            'product_id': 'Product',
            'product_tmpl_id': 'Template',
            'compute_price': 'Compute Type',
        }

        for item in self:
            if not item.pricelist_id:
                continue

            changes = []
            for field, label in field_labels.items():
                if field in vals:
                    old_value = getattr(item, field)
                    new_value = vals.get(field)

                    old_str = self._format_value(old_value)

                    new_str = str(new_value)
                    if self._fields[field].type == 'many2one' and new_value:
                        new_rec = self.env[self._fields[field].comodel_name].browse(new_value)
                        new_str = new_rec.display_name

                    if old_str != new_str:
                        changes.append(f"{label}: {old_str} &#8594; {new_str}")

            if changes:
                target = item._get_target_name()
                header = f"<b>Updated Rule: {target}</b>"
                body = "<ul>" + "".join([f"<li>{c}</li>" for c in changes]) + "</ul>"

                item.pricelist_id.message_post(body=Markup(header + body))

        return super(PricelistItem, self).write(vals)

    @api.model_create_multi
    def create(self, vals_list):
        items = super(PricelistItem, self).create(vals_list)
        for item in items:
            if item.pricelist_id:
                target = item._get_target_name()
                # Create a simple summary
                details = []
                if item.min_quantity > 0:
                    details.append(f"Min Qty: {item.min_quantity}")
                if item.fixed_price > 0:
                    details.append(f"Price: {item.fixed_price}")

                detail_str = f" ({', '.join(details)})" if details else ""

                msg = f"<b>Added Rule:</b> {target}{detail_str}"
                item.pricelist_id.message_post(body=Markup(msg))
        return items

    def unlink(self):
        for item in self:
            if item.pricelist_id:
                target = item._get_target_name()
                msg = f"<b>Deleted Rule:</b> {target}"
                item.pricelist_id.message_post(body=Markup(msg))
        return super(PricelistItem, self).unlink()


    def _get_target_name(self):
        if self.applied_on == '3_global':
            return "All Products"
        elif self.applied_on == '2_product_category' and self.categ_id:
            return self.categ_id.display_name
        elif self.applied_on == '1_product' and self.product_tmpl_id:
            return self.product_tmpl_id.display_name
        elif self.applied_on == '0_product_variant' and self.product_id:
            return self.product_id.display_name
        return "Undefined"

    def _format_value(self, value):
        if hasattr(value, 'display_name'):
            return value.display_name
        elif hasattr(value, 'name'):
            return value.name
        return str(value)