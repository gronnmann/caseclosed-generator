"""ReportLab PDF template for PersonOfInterestForm evidence."""

from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm, mm
from reportlab.platypus import Image, Paragraph, Spacer, Table, TableStyle

from caseclosed.models.evidence import PersonOfInterestForm
from caseclosed.pdf_templates._common import HEADING_STYLE, NORMAL, SMALL, esc, hr, make_doc

_STYLES = getSampleStyleSheet()

_HW_STYLE = ParagraphStyle(
    "Handwriting",
    parent=NORMAL,
    fontSize=12,
    fontName="Helvetica-Oblique",
)

_GRID_STYLE = TableStyle([
    ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
    ("VALIGN", (0, 0), (-1, -1), "TOP"),
    ("TOPPADDING", (0, 0), (-1, -1), 4),
    ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ("LEFTPADDING", (0, 0), (-1, -1), 6),
])


def _field(label: str, value: str) -> list[object]:
    return [
        Paragraph(f"<b>{esc(label)}</b>", SMALL),
        Paragraph(esc(value or "N/A"), _HW_STYLE),
    ]


def render_poi_form(
    item: PersonOfInterestForm,
    path: Path,
    portrait_path: str | None = None,
    hw_font: str = "Helvetica",
) -> None:
    doc = make_doc(path)
    story: list[object] = []

    full_name = " ".join(filter(None, [item.name, item.middle_name, item.last_name]))

    # Title row with optional portrait
    title_para = Paragraph("<b>Person of Interest (PoI)</b>", ParagraphStyle(
        "POITitle", parent=_STYLES["Heading1"], fontSize=16, spaceAfter=2,
    ))

    if portrait_path and Path(portrait_path).exists():
        try:
            img = Image(portrait_path, width=3 * cm, height=3.6 * cm)
            title_table = Table([[title_para, img]], colWidths=[None, 3.5 * cm])
            title_table.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP")]))
            story.append(title_table)
        except Exception:
            story.append(title_para)
    else:
        story.append(title_para)

    # --- Personal Information ---
    story.append(Paragraph("<b>Personal Information</b>", HEADING_STYLE))
    personal_data = [
        [_field("First Name", item.name), _field("Middle Name", item.middle_name), _field("Last Name", item.last_name)],
        [_field("Alias / Maiden Name", item.nickname or "N/A"), _field("Date of Birth", item.date_of_birth), _field("Country of Birth", item.country_of_birth or "N/A")],
        [_field("Nationality", item.nationality or "N/A"), _field("National Identity Number", item.id_number or "N/A"), _field("Occupation", item.occupation or "N/A")],
    ]
    t = Table(personal_data, colWidths=[None, None, None])
    t.setStyle(_GRID_STYLE)
    story.append(t)

    # --- Contact Information ---
    story.append(Paragraph("<b>Contact Information</b>", HEADING_STYLE))
    t1 = Table(
        [[_field("Phone (Country Code)", item.phone_country_code), _field("Phone Number", item.phone_number)]],
        colWidths=[5 * cm, None],
    )
    t1.setStyle(_GRID_STYLE)
    story.append(t1)

    t2 = Table(
        [[_field("Home Address", item.street_address), _field("City", item.city), _field("Zip Code", item.postal_code), _field("Country", item.country)]],
        colWidths=[None, None, 3 * cm, None],
    )
    t2.setStyle(_GRID_STYLE)
    story.append(t2)

    # --- Physical Description ---
    story.append(Paragraph("<b>Physical Description</b>", HEADING_STYLE))
    t3 = Table([
        [_field("Height (cm)", item.height_cm or "N/A"), _field("Weight (kg)", item.weight_kg or "N/A")],
        [_field("Eye Color", item.eye_color or "N/A"), _field("Hair Color", item.hair_color or "N/A")],
    ], colWidths=[None, None])
    t3.setStyle(_GRID_STYLE)
    story.append(t3)

    t3b = Table([[_field("Shoe Size (EU/cm)", item.shoe_size_eu or "N/A")]], colWidths=[None])
    t3b.setStyle(_GRID_STYLE)
    story.append(t3b)

    # --- Additional Information ---
    story.append(Paragraph("<b>Additional Information</b>", HEADING_STYLE))
    t4 = Table([
        [_field("Vehicle (License plate)", item.vehicle_plates or "N/A"), _field("Employer", item.employer or "N/A")],
        [_field("Prior arrests (YES/NO)", "Yes" if item.prior_arrests else "No"), _field("Criminal record (YES/NO)", "Yes" if item.prior_convictions else "No")],
    ], colWidths=[None, None])
    t4.setStyle(_GRID_STYLE)
    story.append(t4)

    # --- Disclaimer + Signature ---
    story.append(Spacer(1, 6 * mm))
    story.append(Paragraph(
        "I hereby confirm that all the information provided in this form is true and accurate "
        "to the best of my knowledge. I understand that providing false or misleading information "
        "may have legal consequences.",
        ParagraphStyle("Disclaimer", parent=NORMAL, fontSize=8),
    ))
    story.append(Spacer(1, 4 * mm))
    story.append(Paragraph("<b>Signature</b>", NORMAL))
    sig_style = ParagraphStyle("Signature", parent=NORMAL, fontSize=16, fontName="Helvetica-Oblique")
    story.append(Paragraph(esc(item.signature or full_name), sig_style))
    story.append(hr())

    doc.build(story)
