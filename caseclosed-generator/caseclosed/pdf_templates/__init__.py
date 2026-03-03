"""ReportLab-based PDF templates for evidence types."""

from caseclosed.pdf_templates.email import render_email
from caseclosed.pdf_templates.facebook_post import render_facebook_post
from caseclosed.pdf_templates.instagram_post import render_instagram_post
from caseclosed.pdf_templates.invoice import render_invoice
from caseclosed.pdf_templates.phone_log import render_phone_log
from caseclosed.pdf_templates.poi_form import render_poi_form
from caseclosed.pdf_templates.receipt import render_receipt
from caseclosed.pdf_templates.sms_log import render_sms_log

__all__ = [
    "render_email",
    "render_facebook_post",
    "render_instagram_post",
    "render_invoice",
    "render_phone_log",
    "render_poi_form",
    "render_receipt",
    "render_sms_log",
]
