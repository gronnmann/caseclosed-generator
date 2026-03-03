"""ReportLab PDF template for PhoneLog evidence."""

from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.units import cm
from reportlab.platypus import Paragraph, Table, TableStyle

from caseclosed.models.evidence import PhoneLog
from caseclosed.pdf_templates._common import NORMAL, TITLE_STYLE, hr, make_doc, meta_table

_DIRECTION_ICONS = {"incoming": "\u2190", "outgoing": "\u2192", "missed": "\u2717"}


def render_phone_log(item: PhoneLog, path: Path) -> None:
    doc = make_doc(path)
    story: list[object] = []

    story.append(Paragraph("PHONE CALL LOG", TITLE_STYLE))
    story.append(meta_table([("Owner:", item.owner_name), ("Phone Number:", item.phone_number)]))
    story.append(hr())

    header = ["Timestamp", "Direction", "Other Party", "Duration"]
    data: list[list[str | Paragraph]] = [
        [Paragraph(f"<b>{h}</b>", NORMAL) for h in header]
    ]
    for e in item.entries:
        icon = _DIRECTION_ICONS.get(e.direction, "?")
        data.append([
            e.timestamp,
            f"{icon} {e.direction}",
            e.other_party,
            e.duration or "\u2014",
        ])

    t = Table(data, colWidths=[4 * cm, 3 * cm, None, 2.5 * cm], repeatRows=1)
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#f5f5f5")),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("FONTSIZE", (0, 1), (-1, -1), 9),
    ]))
    story.append(t)

    doc.build(story)
