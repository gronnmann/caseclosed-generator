"""ReportLab PDF template for Invoice evidence."""

from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.units import cm, mm
from reportlab.platypus import Paragraph, Spacer, Table, TableStyle

from caseclosed.models.evidence import Invoice
from caseclosed.pdf_templates._common import NORMAL, TITLE_STYLE, esc, make_doc


def render_invoice(item: Invoice, path: Path) -> None:
    doc = make_doc(path)
    story: list[object] = []

    story.append(Paragraph("INVOICE", TITLE_STYLE))
    story.append(Spacer(1, 2 * mm))

    # Invoice meta
    meta_data = [
        [Paragraph(f"<b>Invoice #:</b> {esc(item.invoice_number)}", NORMAL),
         Paragraph(f"<b>Date:</b> {esc(item.date)}", NORMAL)],
    ]
    meta_t = Table(meta_data, colWidths=[None, None])
    meta_t.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP")]))
    story.append(meta_t)
    story.append(Spacer(1, 4 * mm))

    # Seller / Buyer
    seller_buyer = [
        [Paragraph("<b>From:</b>", NORMAL), Paragraph("<b>To:</b>", NORMAL)],
        [Paragraph(f"{esc(item.seller_name)}<br/>{esc(item.seller_address)}", NORMAL),
         Paragraph(f"{esc(item.buyer_name)}<br/>{esc(item.buyer_address)}", NORMAL)],
    ]
    sb_t = Table(seller_buyer, colWidths=[None, None])
    sb_t.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 2),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
    ]))
    story.append(sb_t)
    story.append(Spacer(1, 6 * mm))

    # Line items
    header = ["Description", "Qty", "Unit Price", "Total"]
    data: list[list[str | Paragraph]] = [
        [Paragraph(f"<b>{h}</b>", NORMAL) for h in header]
    ]
    for li in item.items:
        data.append([li.description, str(li.quantity), li.unit_price, li.total])

    t = Table(data, colWidths=[None, 2 * cm, 3 * cm, 3 * cm], repeatRows=1)
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#f5f5f5")),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
        ("ALIGN", (1, 0), (-1, -1), "RIGHT"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("FONTSIZE", (0, 1), (-1, -1), 9),
    ]))
    story.append(t)

    # Totals
    story.append(Spacer(1, 4 * mm))
    totals_data: list[list[str | Paragraph]] = [
        ["", "", Paragraph("<b>Subtotal:</b>", NORMAL), item.subtotal],
    ]
    if item.tax:
        totals_data.append(["", "", Paragraph("<b>Tax:</b>", NORMAL), item.tax])
    totals_data.append(["", "", Paragraph("<b>Total:</b>", NORMAL), Paragraph(f"<b>{esc(item.total)}</b>", NORMAL)])

    tt = Table(totals_data, colWidths=[None, None, 3 * cm, 3 * cm])
    tt.setStyle(TableStyle([
        ("ALIGN", (-1, 0), (-1, -1), "RIGHT"),
        ("LINEABOVE", (-2, -1), (-1, -1), 1, colors.black),
        ("TOPPADDING", (0, 0), (-1, -1), 2),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
    ]))
    story.append(tt)

    if item.payment_terms:
        story.append(Spacer(1, 6 * mm))
        story.append(Paragraph(f"<b>Payment Terms:</b> {esc(item.payment_terms)}", NORMAL))

    if item.notes:
        story.append(Spacer(1, 4 * mm))
        story.append(Paragraph(f"<b>Notes:</b> {esc(item.notes)}", NORMAL))

    doc.build(story)
