"""ReportLab PDF template for FacebookPost evidence."""

from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, Spacer

from caseclosed.models.evidence import FacebookPost
from caseclosed.pdf_templates._common import NORMAL, esc, hr, make_doc


def render_facebook_post(item: FacebookPost, path: Path) -> None:
    doc = make_doc(path)
    story: list[object] = []

    author_style = ParagraphStyle("FBAuthor", parent=NORMAL, fontSize=13, fontName="Helvetica-Bold")
    date_style = ParagraphStyle("FBDate", parent=NORMAL, fontSize=9, textColor=colors.HexColor("#999999"))
    content_style = ParagraphStyle("FBContent", parent=NORMAL, fontSize=12, leading=16, spaceBefore=6, spaceAfter=6)
    likes_style = ParagraphStyle("FBLikes", parent=NORMAL, fontSize=10, textColor=colors.HexColor("#666666"))

    story.append(Paragraph(esc(item.author_name), author_style))
    story.append(Paragraph(esc(item.date), date_style))
    story.append(Spacer(1, 3 * mm))

    for para in item.content.split("\n\n"):
        para = para.strip()
        if not para:
            continue
        story.append(Paragraph(esc(para).replace("\n", "<br/>"), content_style))

    story.append(Spacer(1, 3 * mm))
    story.append(Paragraph(f"\U0001F44D {item.likes}", likes_style))

    if item.comments:
        story.append(hr())
        comment_style = ParagraphStyle("FBComment", parent=NORMAL, fontSize=10, leftIndent=12, spaceBefore=3)
        for c in item.comments:
            story.append(Paragraph(esc(c), comment_style))

    doc.build(story)
