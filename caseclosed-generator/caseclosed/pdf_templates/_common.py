"""Shared ReportLab styles and helpers for PDF templates."""

from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import (
    HRFlowable,
    Paragraph,
    SimpleDocTemplate,
    Table,
    TableStyle,
)

_STYLES = getSampleStyleSheet()

TITLE_STYLE = ParagraphStyle(
    "EvidenceTitle",
    parent=_STYLES["Heading1"],
    fontSize=14,
    alignment=1,  # center
    spaceAfter=6,
)

HEADING_STYLE = ParagraphStyle(
    "EvidenceHeading",
    parent=_STYLES["Heading2"],
    fontSize=11,
    spaceBefore=10,
    spaceAfter=4,
)

NORMAL = ParagraphStyle(
    "EvidenceNormal",
    parent=_STYLES["Normal"],
    fontSize=10,
    leading=13,
)

SMALL = ParagraphStyle(
    "EvidenceSmall",
    parent=_STYLES["Normal"],
    fontSize=8,
    leading=10,
    textColor=colors.grey,
)


def make_doc(path: Path, **kwargs: object) -> SimpleDocTemplate:
    return SimpleDocTemplate(
        str(path),
        pagesize=A4,
        leftMargin=2 * cm,
        rightMargin=2 * cm,
        topMargin=2 * cm,
        bottomMargin=2 * cm,
        **kwargs,
    )


def hr() -> HRFlowable:
    return HRFlowable(width="100%", thickness=0.5, color=colors.grey, spaceAfter=6, spaceBefore=6)


def meta_table(rows: list[tuple[str, str]]) -> Table:
    """Build a two-column label/value metadata table."""
    data = [
        [Paragraph(f"<b>{label}</b>", NORMAL), Paragraph(value, NORMAL)]
        for label, value in rows
    ]
    t = Table(data, colWidths=[4.5 * cm, None], hAlign="LEFT")
    t.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 2),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
    ]))
    return t


def esc(text: str) -> str:
    """Escape XML special characters for ReportLab Paragraph markup."""
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )
