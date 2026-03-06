"""ReportLab PDF template for Receipt evidence."""

from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import cm, mm
from reportlab.platypus import HRFlowable, Paragraph, SimpleDocTemplate, Spacer

from caseclosed.models.evidence import Receipt
from caseclosed.pdf_templates._common import NORMAL, esc


def render_receipt(item: Receipt, path: Path) -> None:
    # Receipts are narrow, like a real thermal receipt
    doc = SimpleDocTemplate(
        str(path),
        pagesize=(8 * cm, 100 * cm),
        leftMargin=0.5 * cm,
        rightMargin=0.5 * cm,
        topMargin=1 * cm,
        bottomMargin=1 * cm,
    )
    story: list[object] = []

    center_style = ParagraphStyle("RCenter", parent=NORMAL, alignment=1, fontSize=10)
    center_bold = ParagraphStyle("RCenterBold", parent=center_style, fontName="Courier-Bold", fontSize=11)
    mono = ParagraphStyle("RMono", parent=NORMAL, fontName="Courier", fontSize=8, leading=10)
    mono_bold = ParagraphStyle("RMonoBold", parent=mono, fontName="Courier-Bold")

    story.append(Paragraph(esc(item.store_name), center_bold))
    if item.store_address:
        story.append(Paragraph(esc(item.store_address), ParagraphStyle("RAddr", parent=center_style, fontSize=8)))
    story.append(Spacer(1, 3 * mm))
    story.append(Paragraph(esc(item.date), center_style))
    story.append(Spacer(1, 2 * mm))
    story.append(HRFlowable(width="100%", thickness=0.5, color=colors.black, dash=[2, 2], spaceAfter=4, spaceBefore=4))

    # Items
    for li in item.items:
        qty_str = f"{li.quantity}x " if li.quantity > 1 else ""
        story.append(Paragraph(f"{esc(qty_str)}{esc(li.description)}", mono))
        story.append(Paragraph(f"{'':>30}{esc(li.price)}", ParagraphStyle("RPrice", parent=mono, alignment=2)))

    story.append(HRFlowable(width="100%", thickness=0.5, color=colors.black, dash=[2, 2], spaceAfter=4, spaceBefore=4))

    # Totals
    story.append(Paragraph(f"Subtotal: {esc(item.subtotal)}", ParagraphStyle("RSub", parent=mono, alignment=2)))
    if item.tax:
        story.append(Paragraph(f"Tax: {esc(item.tax)}", ParagraphStyle("RTax", parent=mono, alignment=2)))
    story.append(Paragraph(f"TOTAL: {esc(item.total)}", ParagraphStyle("RTotal", parent=mono_bold, alignment=2)))

    story.append(Spacer(1, 3 * mm))

    if item.payment_method:
        story.append(Paragraph(f"Paid: {esc(item.payment_method)}", center_style))
    if item.transaction_id:
        story.append(Paragraph(f"Trans: {esc(item.transaction_id)}", ParagraphStyle("RTrans", parent=center_style, fontSize=8)))

    story.append(Spacer(1, 4 * mm))
    story.append(Paragraph("Thank you!", center_style))

    doc.build(story)
