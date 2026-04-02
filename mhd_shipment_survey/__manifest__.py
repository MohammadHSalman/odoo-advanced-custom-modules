{
    "name": "Shipment Survey (Auto WhatsApp on Delivered)",
    "version": "16.0.1.3",
    "author": "Mohammad Haitham Salman",
    "website": "https://example.com",
    "depends": [
        "survey",
        "mail",
        "eg_shipment_management",
        "odx_freshchat_connector"
    ],
    "summary": "Auto-send Arabic WhatsApp survey link when shipment is Delivered; store responses and history on the shipment",
    "data": [
        "security/ir.model.access.csv",
        "views/shipment_order_views.xml",
        "views/driver_survey_report_wizard_views.xml",
        "views/shipment_survey_history_views.xml",
        "wizard/driver_survey_graph_wizard_views.xml"
    ],
    "license": "LGPL-3",
    "installable": True
}