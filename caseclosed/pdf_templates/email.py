"""ReportLab PDF template for Email evidence."""

from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.units import cm, mm
from reportlab.platypus import Paragraph, Spacer, Table, TableStyle

from caseclosed.models.evidence import Email
from caseclosed.pdf_templates._common import NORMAL, esc, make_doc


def render_email(item: Email, path: Path) -> None:
    doc = make_doc(path)
    story: list[object] = []

    # Header box
    header_rows = [
        ("From:", item.from_address),
        ("To:", item.to_address),
    ]
    if item.cc:
        header_rows.append(("CC:", item.cc))
    header_rows.extend([
        ("Date:", item.date),
        ("Subject:", item.subject),
    ])

    data = [
        [Paragraph(f"<b>{label}</b>", NORMAL), Paragraph(esc(value), NORMAL)]
        for label, value in header_rows
    ]
    header_table = Table(data, colWidths=[2.5 * cm, None])
    header_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#f0f0f0")),
        ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#cccccc")),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
    ]))
    story.append(header_table)
    story.append(Spacer(1, 6 * mm))

    for para in item.body_text.split("\n\n"):
        para = para.strip()
        if not para:
            continue
        story.append(Paragraph(esc(para).replace("\n", "<br/>"), NORMAL))
        story.append(Spacer(1, 3 * mm))

    doc.build(story)
