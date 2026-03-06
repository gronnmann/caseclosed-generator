"""ReportLab-based PDF templates for evidence types."""

from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm, mm
from reportlab.platypus import (
    HRFlowable,
    Image,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from caseclosed.models.evidence import (
    Email,
    FacebookPost,
    InstagramPost,
    Invoice,
    PersonOfInterestForm,
    PhoneLog,
    RawText,
    Receipt,
    SmsLog,
)

_STYLES = getSampleStyleSheet()

# ---------------------------------------------------------------------------
# Shared styles
# ---------------------------------------------------------------------------

_TITLE_STYLE = ParagraphStyle(
    "EvidenceTitle",
    parent=_STYLES["Heading1"],
    fontSize=14,
    alignment=1,  # center
    spaceAfter=6,
)

_HEADING_STYLE = ParagraphStyle(
    "EvidenceHeading",
    parent=_STYLES["Heading2"],
    fontSize=11,
    spaceBefore=10,
    spaceAfter=4,
)

_NORMAL = ParagraphStyle(
    "EvidenceNormal",
    parent=_STYLES["Normal"],
    fontSize=10,
    leading=13,
)

_SMALL = ParagraphStyle(
    "EvidenceSmall",
    parent=_STYLES["Normal"],
    fontSize=8,
    leading=10,
    textColor=colors.grey,
)

_META_LABEL = ParagraphStyle(
    "MetaLabel",
    parent=_STYLES["Normal"],
    fontSize=10,
    fontName="Helvetica-Bold",
)


def _doc(path: Path, **kwargs: object) -> SimpleDocTemplate:
    return SimpleDocTemplate(
        str(path),
        pagesize=A4,
        leftMargin=2 * cm,
        rightMargin=2 * cm,
        topMargin=2 * cm,
        bottomMargin=2 * cm,
        **kwargs,
    )


def _hr() -> HRFlowable:
    return HRFlowable(width="100%", thickness=0.5, color=colors.grey, spaceAfter=6, spaceBefore=6)


def _meta_table(rows: list[tuple[str, str]]) -> Table:
    """Build a two-column label/value metadata table."""
    data = [
        [Paragraph(f"<b>{label}</b>", _NORMAL), Paragraph(value, _NORMAL)]
        for label, value in rows
    ]
    t = Table(data, colWidths=[4.5 * cm, None], hAlign="LEFT")
    t.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 2),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
    ]))
    return t


def _esc(text: str) -> str:
    """Escape XML special characters for ReportLab Paragraph markup."""
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


# ===========================================================================
# Phone Log
# ===========================================================================

_DIRECTION_ICONS = {"incoming": "\u2190", "outgoing": "\u2192", "missed": "\u2717"}


def render_phone_log(item: PhoneLog, path: Path) -> None:
    doc = _doc(path)
    story: list[object] = []

    story.append(Paragraph("PHONE CALL LOG", _TITLE_STYLE))
    story.append(_meta_table([("Owner:", item.owner_name), ("Phone Number:", item.phone_number)]))
    story.append(_hr())

    header = ["Timestamp", "Direction", "Other Party", "Duration"]
    data: list[list[str | Paragraph]] = [
        [Paragraph(f"<b>{h}</b>", _NORMAL) for h in header]
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


# ===========================================================================
# SMS Log
# ===========================================================================


def render_sms_log(item: SmsLog, path: Path) -> None:
    doc = _doc(path)
    story: list[object] = []

    story.append(Paragraph("SMS MESSAGE LOG", _TITLE_STYLE))
    story.append(_meta_table([("Owner:", item.owner_name), ("Phone Number:", item.phone_number)]))
    story.append(_hr())

    page_width = A4[0] - 4 * cm  # usable width
    bubble_width = page_width * 0.7

    for msg in item.messages:
        is_outgoing = msg.direction == "outgoing"
        bg = colors.HexColor("#e1f0ff") if is_outgoing else colors.HexColor("#f0f0f0")
        label = item.owner_name if is_outgoing else msg.other_party

        bubble_content = [
            [Paragraph(f'<font size="7" color="#666666">{_esc(msg.timestamp)} &mdash; {_esc(label)}</font>', _NORMAL)],
            [Paragraph(_esc(msg.text), _NORMAL)],
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


# ===========================================================================
# RawText
# ===========================================================================


def render_raw_text(item: RawText, path: Path, body_image: str | None = None) -> None:
    doc = _doc(path)
    story: list[object] = []

    if body_image:
        try:
            story.append(Image(body_image, width=8 * cm, height=6 * cm))
            story.append(Spacer(1, 4 * mm))
        except Exception:
            pass

    # Split on double-newlines for paragraphs
    for para in item.content.split("\n\n"):
        para = para.strip()
        if not para:
            continue
        story.append(Paragraph(_esc(para).replace("\n", "<br/>"), _NORMAL))
        story.append(Spacer(1, 3 * mm))

    doc.build(story)


# ===========================================================================
# Email
# ===========================================================================


def render_email(item: Email, path: Path) -> None:
    doc = _doc(path)
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
        [Paragraph(f"<b>{label}</b>", _NORMAL), Paragraph(_esc(value), _NORMAL)]
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
        story.append(Paragraph(_esc(para).replace("\n", "<br/>"), _NORMAL))
        story.append(Spacer(1, 3 * mm))

    doc.build(story)


# ===========================================================================
# Person of Interest Form
# ===========================================================================


def render_poi_form(
    item: PersonOfInterestForm,
    path: Path,
    portrait_path: str | None = None,
    hw_font: str = "Helvetica",
) -> None:
    doc = _doc(path) 
    story: list[object] = []

    # We'll use Helvetica-Oblique as a stand-in for handwriting since
    # ReportLab can't load Google Fonts without TTF registration.
    # The "handwriting" effect is conveyed via italic + larger size.
    hw_style = ParagraphStyle(
        "Handwriting",
        parent=_NORMAL,
        fontSize=12,
        fontName="Helvetica-Oblique",
    )

    def _field(label: str, value: str) -> list[object]:
        return [
            Paragraph(f"<b>{_esc(label)}</b>", _SMALL),
            Paragraph(_esc(value or "N/A"), hw_style),
        ]

    # Title row with optional portrait
    title_para = Paragraph("<b>Person of Interest (PoI)</b>", ParagraphStyle(
        "POITitle", parent=_STYLES["Heading1"], fontSize=16, spaceAfter=2,
    ))

    if portrait_path and Path(portrait_path).exists():
        try:
            img = Image(portrait_path, width=3 * cm, height=3.6 * cm)
            title_table = Table([[title_para, img]], colWidths=[None, 3.5 * cm])
            title_table.setStyle(TableStyle([
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ]))
            story.append(title_table)
        except Exception:
            story.append(title_para)
    else:
        story.append(title_para)

    # --- Personal Information ---
    story.append(Paragraph("<b>Personal Information</b>", _HEADING_STYLE))

    full_name = " ".join(filter(None, [item.name, item.middle_name, item.last_name]))

    personal_data = [
        [_field("First Name", item.name), _field("Middle Name", item.middle_name), _field("Last Name", item.last_name)],
        [_field("Alias / Maiden Name", item.nickname or "N/A"), _field("Date of Birth", item.date_of_birth), _field("Country of Birth", item.country_of_birth or "N/A")],
        [_field("Nationality", item.nationality or "N/A"), _field("National Identity Number", item.id_number or "N/A"), _field("Occupation", item.occupation or "N/A")],
    ]
    t = Table(personal_data, colWidths=[None, None, None])
    t.setStyle(TableStyle([
        ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
    ]))
    story.append(t)

    # --- Contact Information ---
    story.append(Paragraph("<b>Contact Information</b>", _HEADING_STYLE))

    contact_data1 = [
        [_field("Phone (Country Code)", item.phone_country_code), _field("Phone Number", item.phone_number)],
    ]
    t1 = Table(contact_data1, colWidths=[5 * cm, None])
    t1.setStyle(TableStyle([
        ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
    ]))
    story.append(t1)

    contact_data2 = [
        [_field("Home Address", item.street_address), _field("City", item.city), _field("Zip Code", item.postal_code), _field("Country", item.country)],
    ]
    t2 = Table(contact_data2, colWidths=[None, None, 3 * cm, None])
    t2.setStyle(TableStyle([
        ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
    ]))
    story.append(t2)

    # --- Physical Description ---
    story.append(Paragraph("<b>Physical Description</b>", _HEADING_STYLE))

    phys_data = [
        [_field("Height (cm)", item.height_cm or "N/A"), _field("Weight (kg)", item.weight_kg or "N/A")],
        [_field("Eye Color", item.eye_color or "N/A"), _field("Hair Color", item.hair_color or "N/A")],
    ]
    t3 = Table(phys_data, colWidths=[None, None])
    t3.setStyle(TableStyle([
        ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
    ]))
    story.append(t3)

    shoe_data = [
        [_field("Shoe Size (EU/cm)", item.shoe_size_eu or "N/A")],
    ]
    t3b = Table(shoe_data, colWidths=[None])
    t3b.setStyle(TableStyle([
        ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
    ]))
    story.append(t3b)

    # --- Additional Information ---
    story.append(Paragraph("<b>Additional Information</b>", _HEADING_STYLE))

    add_data = [
        [_field("Vehicle (License plate)", item.vehicle_plates or "N/A"), _field("Employer", item.employer or "N/A")],
        [_field("Prior arrests (YES/NO)", "Yes" if item.prior_arrests else "No"), _field("Criminal record (YES/NO)", "Yes" if item.prior_convictions else "No")],
    ]
    t4 = Table(add_data, colWidths=[None, None])
    t4.setStyle(TableStyle([
        ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
    ]))
    story.append(t4)

    # --- Disclaimer + Signature ---
    story.append(Spacer(1, 6 * mm))
    story.append(Paragraph(
        "I hereby confirm that all the information provided in this form is true and accurate "
        "to the best of my knowledge. I understand that providing false or misleading information "
        "may have legal consequences.",
        ParagraphStyle("Disclaimer", parent=_NORMAL, fontSize=8),
    ))
    story.append(Spacer(1, 4 * mm))
    story.append(Paragraph("<b>Signature</b>", _NORMAL))
    sig_style = ParagraphStyle("Signature", parent=_NORMAL, fontSize=16, fontName="Helvetica-Oblique")
    story.append(Paragraph(_esc(item.signature or full_name), sig_style))
    story.append(_hr())

    doc.build(story)


# ===========================================================================
# Facebook Post
# ===========================================================================


def render_facebook_post(item: FacebookPost, path: Path) -> None:
    doc = _doc(path)
    story: list[object] = []

    # Post card
    author_style = ParagraphStyle("FBAuthor", parent=_NORMAL, fontSize=13, fontName="Helvetica-Bold")
    date_style = ParagraphStyle("FBDate", parent=_NORMAL, fontSize=9, textColor=colors.HexColor("#999999"))
    content_style = ParagraphStyle("FBContent", parent=_NORMAL, fontSize=12, leading=16, spaceBefore=6, spaceAfter=6)
    likes_style = ParagraphStyle("FBLikes", parent=_NORMAL, fontSize=10, textColor=colors.HexColor("#666666"))

    story.append(Paragraph(_esc(item.author_name), author_style))
    story.append(Paragraph(_esc(item.date), date_style))
    story.append(Spacer(1, 3 * mm))

    for para in item.content.split("\n\n"):
        para = para.strip()
        if not para:
            continue
        story.append(Paragraph(_esc(para).replace("\n", "<br/>"), content_style))

    story.append(Spacer(1, 3 * mm))
    story.append(Paragraph(f"\U0001F44D {item.likes}", likes_style))

    if item.comments:
        story.append(_hr())
        comment_style = ParagraphStyle("FBComment", parent=_NORMAL, fontSize=10, leftIndent=12, spaceBefore=3)
        for c in item.comments:
            story.append(Paragraph(_esc(c), comment_style))

    doc.build(story)


# ===========================================================================
# Instagram Post
# ===========================================================================


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

    username_style = ParagraphStyle("IGUser", parent=_NORMAL, fontSize=12, fontName="Helvetica-Bold")
    caption_style = ParagraphStyle("IGCaption", parent=_NORMAL, fontSize=11, leading=14)
    likes_style = ParagraphStyle("IGLikes", parent=_NORMAL, fontSize=11, fontName="Helvetica-Bold")
    date_style = ParagraphStyle("IGDate", parent=_NORMAL, fontSize=8, textColor=colors.HexColor("#999999"))

    story.append(Paragraph(_esc(item.username), username_style))
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
        f"<b>{_esc(item.username)}</b> {_esc(item.caption)}",
        caption_style,
    ))
    story.append(Spacer(1, 2 * mm))
    story.append(Paragraph(_esc(item.date), date_style))

    doc.build(story)


# ===========================================================================
# Invoice
# ===========================================================================


def render_invoice(item: Invoice, path: Path) -> None:
    doc = _doc(path)
    story: list[object] = []

    story.append(Paragraph("INVOICE", _TITLE_STYLE))
    story.append(Spacer(1, 2 * mm))

    # Invoice meta
    meta_data = [
        [Paragraph(f"<b>Invoice #:</b> {_esc(item.invoice_number)}", _NORMAL),
         Paragraph(f"<b>Date:</b> {_esc(item.date)}", _NORMAL)],
    ]
    meta_t = Table(meta_data, colWidths=[None, None])
    meta_t.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
    ]))
    story.append(meta_t)
    story.append(Spacer(1, 4 * mm))

    # Seller / Buyer
    seller_buyer = [
        [Paragraph("<b>From:</b>", _NORMAL), Paragraph("<b>To:</b>", _NORMAL)],
        [Paragraph(f"{_esc(item.seller_name)}<br/>{_esc(item.seller_address)}", _NORMAL),
         Paragraph(f"{_esc(item.buyer_name)}<br/>{_esc(item.buyer_address)}", _NORMAL)],
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
        [Paragraph(f"<b>{h}</b>", _NORMAL) for h in header]
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
        ["", "", Paragraph("<b>Subtotal:</b>", _NORMAL), item.subtotal],
    ]
    if item.tax:
        totals_data.append(["", "", Paragraph("<b>Tax:</b>", _NORMAL), item.tax])
    totals_data.append(["", "", Paragraph("<b>Total:</b>", _NORMAL), Paragraph(f"<b>{_esc(item.total)}</b>", _NORMAL)])

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
        story.append(Paragraph(f"<b>Payment Terms:</b> {_esc(item.payment_terms)}", _NORMAL))

    if item.notes:
        story.append(Spacer(1, 4 * mm))
        story.append(Paragraph(f"<b>Notes:</b> {_esc(item.notes)}", _NORMAL))

    doc.build(story)


# ===========================================================================
# Receipt
# ===========================================================================


def render_receipt(item: Receipt, path: Path) -> None:
    # Receipts are narrow, like a real thermal receipt
    doc = SimpleDocTemplate(
        str(path),
        pagesize=(8 * cm, 100 * cm),  # narrow, auto-height via keepTogetherSplitAtTop
        leftMargin=0.5 * cm,
        rightMargin=0.5 * cm,
        topMargin=1 * cm,
        bottomMargin=1 * cm,
    )
    story: list[object] = []

    center_style = ParagraphStyle("RCenter", parent=_NORMAL, alignment=1, fontSize=10)
    center_bold = ParagraphStyle("RCenterBold", parent=center_style, fontName="Courier-Bold", fontSize=11)
    mono = ParagraphStyle("RMono", parent=_NORMAL, fontName="Courier", fontSize=8, leading=10)
    mono_bold = ParagraphStyle("RMonoBold", parent=mono, fontName="Courier-Bold")

    story.append(Paragraph(_esc(item.store_name), center_bold))
    if item.store_address:
        story.append(Paragraph(_esc(item.store_address), ParagraphStyle("RAddr", parent=center_style, fontSize=8)))
    story.append(Spacer(1, 3 * mm))
    story.append(Paragraph(_esc(item.date), center_style))
    story.append(Spacer(1, 2 * mm))
    story.append(HRFlowable(width="100%", thickness=0.5, color=colors.black, dash=[2, 2], spaceAfter=4, spaceBefore=4))

    # Items
    for li in item.items:
        qty_str = f"{li.quantity}x " if li.quantity > 1 else ""
        story.append(Paragraph(f"{_esc(qty_str)}{_esc(li.description)}", mono))
        story.append(Paragraph(f"{'':>30}{_esc(li.price)}", ParagraphStyle("RPrice", parent=mono, alignment=2)))

    story.append(HRFlowable(width="100%", thickness=0.5, color=colors.black, dash=[2, 2], spaceAfter=4, spaceBefore=4))

    # Totals
    story.append(Paragraph(f"Subtotal: {_esc(item.subtotal)}", ParagraphStyle("RSub", parent=mono, alignment=2)))
    if item.tax:
        story.append(Paragraph(f"Tax: {_esc(item.tax)}", ParagraphStyle("RTax", parent=mono, alignment=2)))
    story.append(Paragraph(f"TOTAL: {_esc(item.total)}", ParagraphStyle("RTotal", parent=mono_bold, alignment=2)))

    story.append(Spacer(1, 3 * mm))

    if item.payment_method:
        story.append(Paragraph(f"Paid: {_esc(item.payment_method)}", center_style))
    if item.transaction_id:
        story.append(Paragraph(f"Trans: {_esc(item.transaction_id)}", ParagraphStyle("RTrans", parent=center_style, fontSize=8)))

    story.append(Spacer(1, 4 * mm))
    story.append(Paragraph("Thank you!", center_style))

    doc.build(story)
