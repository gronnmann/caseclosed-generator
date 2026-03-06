"""ReportLab PDF template for InstagramPost evidence."""

from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import cm, mm
from reportlab.platypus import Image, Paragraph, SimpleDocTemplate, Spacer

from caseclosed.models.evidence import InstagramPost
from caseclosed.pdf_templates._common import NORMAL, esc


def render_instagram_post(item: InstagramPost, path: Path, image_path: str | None = None) -> None:
    doc = SimpleDocTemplate(
        str(path),
        pagesize=A4,
        leftMargin=3 * cm,
        rightMargin=3 * cm,
        topMargin=2 * cm,
        bottomMargin=2 * cm,
    )
    story: list[object] = []

    username_style = ParagraphStyle("IGUser", parent=NORMAL, fontSize=12, fontName="Helvetica-Bold")
    caption_style = ParagraphStyle("IGCaption", parent=NORMAL, fontSize=11, leading=14)
    likes_style = ParagraphStyle("IGLikes", parent=NORMAL, fontSize=11, fontName="Helvetica-Bold")
    date_style = ParagraphStyle("IGDate", parent=NORMAL, fontSize=8, textColor=colors.HexColor("#999999"))

    story.append(Paragraph(esc(item.username), username_style))
    story.append(Spacer(1, 3 * mm))

    if image_path and Path(image_path).exists():
        try:
            usable = A4[0] - 6 * cm
            img = Image(image_path, width=usable, height=usable)
            story.append(img)
            story.append(Spacer(1, 3 * mm))
        except Exception:
            pass

    story.append(Paragraph(f"\u2764\ufe0f {item.likes} likes", likes_style))
    story.append(Spacer(1, 2 * mm))
    story.append(Paragraph(
        f"<b>{esc(item.username)}</b> {esc(item.caption)}",
        caption_style,
    ))
    story.append(Spacer(1, 2 * mm))
    story.append(Paragraph(esc(item.date), date_style))

    doc.build(story)
