"""ReportLab PDF template for SmsLog evidence."""

from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import cm, mm
from reportlab.platypus import Paragraph, Spacer, Table, TableStyle

from caseclosed.models.evidence import SmsLog
from caseclosed.pdf_templates._common import NORMAL, TITLE_STYLE, esc, hr, make_doc, meta_table


def render_sms_log(item: SmsLog, path: Path) -> None:
    doc = make_doc(path)
    story: list[object] = []

    story.append(Paragraph("SMS MESSAGE LOG", TITLE_STYLE))
    story.append(meta_table([
        ("Owner:", item.owner_name),
        ("Phone Number:", item.phone_number),
        ("Conversation with:", item.other_party),
    ]))
    story.append(hr())

    page_width = A4[0] - 4 * cm  # usable width
    bubble_width = page_width * 0.7

    for msg in item.messages:
        is_outgoing = msg.direction == "outgoing"
        bg = colors.HexColor("#e1f0ff") if is_outgoing else colors.HexColor("#f0f0f0")
        label = item.owner_name if is_outgoing else item.other_party

        bubble_content = [
            [Paragraph(f'<font size="7" color="#666666">{esc(msg.timestamp)} &mdash; {esc(label)}</font>', NORMAL)],
            [Paragraph(esc(msg.text), NORMAL)],
        ]
        bubble = Table(bubble_content, colWidths=[bubble_width])
        bubble.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), bg),
            ("ROUNDEDCORNERS", [6, 6, 6, 6]),
            ("LEFTPADDING", (0, 0), (-1, -1), 8),
            ("RIGHTPADDING", (0, 0), (-1, -1), 8),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ]))

        # Wrap in outer table for alignment
        if is_outgoing:
            row = [["", bubble]]
            wrapper = Table(row, colWidths=[page_width - bubble_width, bubble_width])
        else:
            row = [[bubble, ""]]
            wrapper = Table(row, colWidths=[bubble_width, page_width - bubble_width])
        wrapper.setStyle(TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("TOPPADDING", (0, 0), (-1, -1), 0),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
            ("LEFTPADDING", (0, 0), (-1, -1), 0),
            ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ]))
        story.append(wrapper)
        story.append(Spacer(1, 4 * mm))

    doc.build(story)
