"""Export evidence to Typst, LaTeX, and HTML, compiled to PDF."""

import shutil
import subprocess
from pathlib import Path

from rich.console import Console

from caseclosed.models.case import Case
from caseclosed.models.evidence import (
    Email,
    EvidencePlanItem,
    FacebookPost,
    HandwrittenNote,
    InstagramPost,
    InterrogationReport,
    Invoice,
    Letter,
    PersonOfInterestForm,
    PhoneLog,
    RawText,
    Receipt,
    SmsLog,
)
from caseclosed.pdf_templates import (
    render_email,
    render_facebook_post,
    render_instagram_post,
    render_invoice,
    render_phone_log,
    render_poi_form,
    render_receipt,
    render_sms_log,
)
from caseclosed.persistence import images_dir

console = Console()

# Path to bundled resources
_RES_DIR = Path(__file__).resolve().parent.parent / "res"
_DEFAULT_HANDWRITING = "Caveat"


# ---------------------------------------------------------------------------
# Directory helpers
# ---------------------------------------------------------------------------


def _export_dir(case: Case) -> Path:
    from caseclosed.config import settings

    path = settings.cases_dir / case.id / "export"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _src_dir(export_root: Path, plan_id: str) -> Path:
    name = plan_id.replace(" ", "-").replace("/", "-").replace("\\", "-")
    path = export_root / "_src" / name
    path.mkdir(parents=True, exist_ok=True)
    return path


# ---------------------------------------------------------------------------
# Compilation helpers
# ---------------------------------------------------------------------------


def _compile_typst(typ_file: Path) -> Path | None:
    pdf_name = typ_file.with_suffix(".pdf").name
    r = subprocess.run(
        ["typst", "compile", typ_file.name, pdf_name],
        capture_output=True,
        text=True,
        cwd=typ_file.parent.resolve(),
    )
    if r.returncode != 0:
        console.print(f"  [red]typst:[/red] {r.stderr.strip()[:200]}")
        return None
    return typ_file.parent / pdf_name


def _compile_latex(tex_file: Path) -> Path | None:
    r = subprocess.run(
        ["pdflatex", "-interaction=nonstopmode", "-halt-on-error", tex_file.name],
        capture_output=True,
        text=True,
        cwd=tex_file.parent.resolve(),
    )
    if r.returncode != 0:
        err = [line for line in r.stdout.splitlines() if line.startswith("!")]
        console.print(f"  [red]pdflatex:[/red] {err[0] if err else 'failed'}")
        return None
    for ext in (".aux", ".log", ".out"):
        aux = tex_file.with_suffix(ext)
        if aux.exists():
            aux.unlink()
    return tex_file.with_suffix(".pdf")


def _compile_html(html_file: Path) -> Path | None:
    pdf_name = html_file.with_suffix(".pdf").name
    r = subprocess.run(
        ["weasyprint", html_file.name, pdf_name],
        capture_output=True,
        text=True,
        cwd=html_file.parent.resolve(),
    )
    if r.returncode != 0:
        console.print(f"  [red]weasyprint:[/red] {r.stderr.strip()[:200]}")
        return None
    return html_file.parent / pdf_name


_COMPILERS = {
    ".typ": _compile_typst,
    ".tex": _compile_latex,
    ".html": _compile_html,
}


def _build_pdf(src_folder: Path, src_name: str, content: str, pdf_dest: Path) -> bool:
    """Write source file, compile to PDF, move PDF to destination."""
    src_file = src_folder / src_name
    src_file.write_text(content, encoding="utf-8")
    compiler = _COMPILERS.get(src_file.suffix)
    if not compiler:
        return False
    pdf = compiler(src_file)
    if pdf and pdf.exists():
        shutil.move(str(pdf), str(pdf_dest))
        return True
    return False


# ---------------------------------------------------------------------------
# Suspect font lookup & resource helpers
# ---------------------------------------------------------------------------


def _suspect_font(case: Case, name: str) -> str:
    """Get the handwriting font for a suspect by name."""
    for s in case.suspects or []:
        if s.name == name:
            return s.handwriting_font or _DEFAULT_HANDWRITING
    return _DEFAULT_HANDWRITING


def _copy_res(filename: str, dest_folder: Path) -> bool:
    """Copy a file from res/ to dest_folder. Returns True if copied."""
    src = _RES_DIR / filename
    if src.exists():
        shutil.copy2(src, dest_folder / filename)
        return True
    return False


# ---------------------------------------------------------------------------
# Main export
# ---------------------------------------------------------------------------


def export_case(case: Case, evidence_id: str | None = None) -> Path:
    """Export evidence to PDF files. Optionally export a single evidence by plan_id."""
    out = _export_dir(case)
    plan_map: dict[str, EvidencePlanItem] = {p.id: p for p in (case.evidence_plan or [])}

    items = list(case.evidence or [])
    if evidence_id:
        items = [e for e in items if e.plan_id == evidence_id]
        if not items:
            console.print(f"[red]No generated evidence with id '{evidence_id}'[/red]")
            available = sorted(e.plan_id for e in (case.evidence or []))
            console.print(f"Available: {', '.join(available)}")
            return out

    console.print(f"[bold]Exporting {len(items)} evidence items...[/bold]\n")
    pdf_count = 0
    skip_count = 0

    for item in items:
        # Skip image evidence — those are given directly to players
        if item.type == "image":
            skip_count += 1
            continue
        # Skip instagram posts with no image yet
        if item.type == "instagram_post" and not getattr(item, "image_filename", None):
            skip_count += 1
            continue

        plan = plan_map.get(item.plan_id)
        ep = plan.introduced_in_episode if plan else 0
        eid = item.plan_id
        folder = _src_dir(out, eid)

        # --- ReportLab direct-PDF path ---
        rl_ok = _try_reportlab(case, item, plan, folder, out, ep, eid)
        if rl_ok is not None:
            tag = "[green]\u2713[/green]" if rl_ok else "[red]\u2717[/red]"
            pdf_name = f"ep{ep}-{eid}-reportlab.pdf"
            console.print(f"  {tag} {pdf_name}")
            if rl_ok:
                pdf_count += 1
            continue

        # --- Legacy Typst / LaTeX / HTML path ---

        # Copy suspect portrait into source dir for POI forms
        portrait_file: str | None = None
        if isinstance(item, PersonOfInterestForm) and plan and plan.suspect_name:
            suspect = next((s for s in case.suspects if s.name == plan.suspect_name), None)
            if suspect:
                portrait_file = _find_portrait(case, suspect, folder)

        # Copy instagram image into source dir
        ig_image: str | None = None
        if isinstance(item, InstagramPost) and item.image_filename:
            src = images_dir(case.id) / item.image_filename
            if src.exists():
                shutil.copy2(src, folder / item.image_filename)
                ig_image = item.image_filename

        formats = _formats_for(case, item, portrait_file, ig_image, folder)

        for fmt_key, (src_name, content) in formats.items():
            if not content:
                continue
            pdf_name = f"ep{ep}-{eid}-{fmt_key}.pdf"
            ok = _build_pdf(folder, src_name, content, out / pdf_name)
            tag = "[green]\u2713[/green]" if ok else "[red]\u2717[/red]"
            console.print(f"  {tag} {pdf_name}")
            if ok:
                pdf_count += 1

    console.print(f"\n[bold]{pdf_count} PDFs compiled[/bold] \u2192 {out}")
    if skip_count:
        console.print(f"[dim]({skip_count} image/instagram items skipped)[/dim]")
    return out


# ---------------------------------------------------------------------------
# ReportLab dispatch
# ---------------------------------------------------------------------------


def _try_reportlab(
    case: Case,
    item: object,
    plan: EvidencePlanItem | None,
    folder: Path,
    out: Path,
    ep: int,
    eid: str,
) -> bool | None:
    """Try to render the item via ReportLab. Returns True/False on success/failure, None if not handled."""
    pdf_dest = out / f"ep{ep}-{eid}-reportlab.pdf"

    try:
        match item:
            case PhoneLog():
                render_phone_log(item, pdf_dest)
            case SmsLog():
                render_sms_log(item, pdf_dest)
            case Email():
                render_email(item, pdf_dest)
            case PersonOfInterestForm():
                portrait: str | None = None
                if plan and plan.suspect_name:
                    suspect = next((s for s in case.suspects if s.name == plan.suspect_name), None)
                    if suspect:
                        portrait = _find_portrait(case, suspect, folder)
                        if portrait:
                            portrait = str(folder / portrait)
                render_poi_form(item, pdf_dest, portrait_path=portrait)
            case FacebookPost():
                render_facebook_post(item, pdf_dest)
            case InstagramPost():
                ig_path: str | None = None
                if item.image_filename:
                    src = images_dir(case.id) / item.image_filename
                    if src.exists():
                        ig_path = str(src)
                render_instagram_post(item, pdf_dest, image_path=ig_path)
            case Invoice():
                render_invoice(item, pdf_dest)
            case Receipt():
                render_receipt(item, pdf_dest)
            case _:
                return None  # not handled by ReportLab
    except Exception as exc:
        console.print(f"  [red]reportlab error:[/red] {exc!s:.200}")
        return False
    return True


# ---------------------------------------------------------------------------
# Format dispatch (legacy — Typst / LaTeX / HTML)
# ---------------------------------------------------------------------------


def _formats_for(
    case: Case,
    item: object,
    portrait_file: str | None = None,
    ig_image: str | None = None,
    folder: Path | None = None,
) -> dict[str, tuple[str, str]]:
    """Return {format_key: (source_filename, content)} for each output format.

    Only handles types NOT covered by ReportLab (InterrogationReport, Letter, HandwrittenNote).
    """
    match item:
        case InterrogationReport():
            return {
                "typst": ("doc.typ", _interrogation_typst(item)),
            }
        case Letter():
            logo = False
            if folder and item.letter_type in ("intro", "solution"):
                logo = _copy_res("logo.png", folder)
            return {
                "typst": ("doc.typ", _letter_typst(item, logo=logo)),
            }
        case RawText():
            if item.format_hint == "autopsy_report" and folder:
                _copy_res("obduction_body.png", folder)
            return {
                "typst": ("doc.typ", item.text_typst or _rawtext_typst(item)),
                "latex": ("doc.tex", item.text_latex or _rawtext_latex(item)),
                "html": ("doc.html", item.text_html or _rawtext_html(item)),
            }
        case HandwrittenNote():
            font = _suspect_font(case, item.author)
            return {
                "typst": ("doc.typ", _handwritten_typst(item, font)),
                "html": ("doc.html", _handwritten_html(item, font)),
            }
    return {}


# ===========================================================================
# Interrogation
# ===========================================================================


def _interrogation_typst(item: InterrogationReport) -> str:
    rows = "\n".join(
        f"  [*{dl.speaker}:*], [{dl.text}],"
        for dl in item.transcript
    )
    return f"""\
#set page(margin: (x: 2cm, y: 2.5cm))
#set text(font: "Special Elite", size: 11pt)
#set par(justify: true, leading: 0.8em)

#align(center)[
  #text(size: 14pt, weight: "bold")[INTERROGATION TRANSCRIPT]
]

#v(1em)

#table(
  columns: (auto, 1fr),
  stroke: none,
  [*Case Number:*], [{item.case_number}],
  [*Date:*], [{item.date}],
  [*Suspect:*], [{item.suspect_name}],
  [*Interviewer:*], [{item.interviewer}],
)

#line(length: 100%)
#v(0.5em)

#table(
  columns: (auto, 1fr),
  stroke: none,
  column-gutter: 1em,
  row-gutter: 0.6em,
{rows}
)
"""


def _interrogation_latex(item: InterrogationReport) -> str:
    rows = "\n".join(
        f"\\textbf{{{_latex_escape(dl.speaker)}:}} & {_latex_escape(dl.text)} \\\\"
        for dl in item.transcript
    )
    return f"""\
\\documentclass[11pt]{{article}}
\\usepackage[margin=1in]{{geometry}}
\\usepackage{{parskip}}
\\usepackage{{longtable}}
\\usepackage{{array}}
\\begin{{document}}

\\begin{{center}}
\\textbf{{\\Large INTERROGATION TRANSCRIPT}}
\\end{{center}}

\\begin{{tabular}}{{@{{}}ll@{{}}}}
\\textbf{{Case Number:}} & {_latex_escape(item.case_number)} \\\\
\\textbf{{Date:}} & {_latex_escape(item.date)} \\\\
\\textbf{{Suspect:}} & {_latex_escape(item.suspect_name)} \\\\
\\textbf{{Interviewer:}} & {_latex_escape(item.interviewer)} \\\\
\\end{{tabular}}

\\bigskip\\hrule\\bigskip

\\begin{{longtable}}{{@{{}}p{{3.5cm}}p{{10cm}}@{{}}}}
{rows}
\\end{{longtable}}

\\bigskip\\hrule
\\begin{{center}}\\textit{{End of transcript}}\\end{{center}}

\\end{{document}}"""


def _interrogation_html(item: InterrogationReport) -> str:
    rows = "\n".join(
        f'<tr><td class="speaker">{_html_escape(dl.speaker)}:</td>'
        f"<td>{_html_escape(dl.text)}</td></tr>"
        for dl in item.transcript
    )
    return f"""\
<!DOCTYPE html>
<html lang="en">
<head><meta charset="UTF-8">
<title>Interrogation</title>
<style>
  body {{ font-family: 'Courier New', monospace; max-width: 800px; margin: 40px auto; padding: 0 20px; }}
  h1 {{ text-align: center; font-size: 1.3em; }}
  .meta p {{ margin: 2px 0; }}
  table {{ width: 100%; border-collapse: collapse; }}
  td {{ padding: 6px 8px; vertical-align: top; }}
  .speaker {{ font-weight: bold; white-space: nowrap; width: 140px; }}
  hr {{ border: none; border-top: 1px solid #999; margin: 1em 0; }}
</style>
</head>
<body>
<h1>INTERROGATION TRANSCRIPT</h1>
<div class="meta">
  <p><strong>Case Number:</strong> {_html_escape(item.case_number)}</p>
  <p><strong>Date:</strong> {_html_escape(item.date)}</p>
  <p><strong>Suspect:</strong> {_html_escape(item.suspect_name)}</p>
  <p><strong>Interviewer:</strong> {_html_escape(item.interviewer)}</p>
</div>
<hr>
<table>
{rows}
</table>
<hr>
<p style="text-align: center; font-style: italic;">End of transcript</p>
</body>
</html>"""


# ===========================================================================
# Letter
# ===========================================================================


def _letter_typst(item: Letter, *, logo: bool = False) -> str:
    body = item.text_typst or item.body_text
    logo_block = '#image("logo.png", width: 5cm)\n#v(0.5em)\n' if logo else ""
    return f"""\
#set page(margin: (x: 2.5cm, y: 2.5cm))
#set text(font: "New Computer Modern", size: 11pt)
#set par(justify: true)

{logo_block}#align(right)[{item.date or ""}]
#v(0.5em)
*From:* {item.sender} \\
*To:* {item.recipient}

#line(length: 100%)
#v(0.5em)

{body}

#v(2em)
_{item.sender}_
"""


def _letter_latex(item: Letter) -> str:
    return f"""\
\\documentclass[11pt]{{article}}
\\usepackage[margin=1in]{{geometry}}
\\usepackage{{parskip}}
\\begin{{document}}

\\begin{{flushright}}
{_latex_escape(item.date or "")}
\\end{{flushright}}

\\textbf{{From:}} {_latex_escape(item.sender)} \\\\
\\textbf{{To:}} {_latex_escape(item.recipient)}

\\hrule
\\vspace{{1em}}

{_latex_escape(item.body_text)}

\\vspace{{2em}}
\\textit{{{_latex_escape(item.sender)}}}

\\end{{document}}"""


def _letter_html(item: Letter, *, logo: bool = False) -> str:
    logo_img = '<div style="margin-bottom: 1em;"><img src="logo.png" style="width: 200px;"></div>\n' if logo else ""
    return f"""\
<!DOCTYPE html>
<html lang="en">
<head><meta charset="UTF-8">
<title>{_html_escape(item.plan_id)}</title>
<style>
  body {{ font-family: Georgia, serif; max-width: 800px; margin: 40px auto; padding: 0 20px; line-height: 1.6; }}
  .meta p {{ margin: 2px 0; }}
  hr {{ border: none; border-top: 1px solid #999; margin: 1em 0; }}
</style>
</head>
<body>
{logo_img}<p style="text-align: right;">{_html_escape(item.date or "")}</p>
<div class="meta">
  <p><strong>From:</strong> {_html_escape(item.sender)}</p>
  <p><strong>To:</strong> {_html_escape(item.recipient)}</p>
</div>
<hr>
<div style="white-space: pre-wrap;">{_html_escape(item.body_text)}</div>
<p style="margin-top: 2em; font-style: italic;">{_html_escape(item.sender)}</p>
</body>
</html>"""


# ===========================================================================
# RawText fallbacks (used when LLM-generated formatted fields are empty)
# ===========================================================================


def _rawtext_typst(item: RawText) -> str:
    return f"""\
#set page(margin: (x: 2.5cm, y: 2.5cm))
#set text(font: "New Computer Modern", size: 11pt)
#set par(justify: true)

{item.content}
"""


def _rawtext_latex(item: RawText) -> str:
    return f"""\
\\documentclass[11pt]{{article}}
\\usepackage[margin=1in]{{geometry}}
\\usepackage{{parskip}}
\\begin{{document}}

{_latex_escape(item.content)}

\\end{{document}}"""


def _rawtext_html(item: RawText) -> str:
    return f"""\
<!DOCTYPE html>
<html lang="en">
<head><meta charset="UTF-8">
<style>
  body {{ font-family: Georgia, serif; max-width: 800px; margin: 40px auto; padding: 0 20px; line-height: 1.6; }}
</style>
</head>
<body>
<div style="white-space: pre-wrap;">{_html_escape(item.content)}</div>
</body>
</html>"""


# ===========================================================================
# Email
# ===========================================================================


def _email_typst(item: Email) -> str:
    cc_line = f"    [*CC:*], [{item.cc}],\n" if item.cc else ""
    return f"""\
#set page(margin: (x: 2cm, y: 2cm))
#set text(font: "New Computer Modern", size: 10pt)

#rect(fill: rgb("#f0f0f0"), width: 100%, inset: 10pt)[
  #table(
    columns: (auto, 1fr),
    stroke: none,
    row-gutter: 0.2em,
    [*From:*], [{item.from_address}],
    [*To:*], [{item.to_address}],
{cc_line}    [*Date:*], [{item.date}],
    [*Subject:*], [*{item.subject}*],
  )
]

#v(0.5em)

{item.body_text}
"""


def _email_latex(item: Email) -> str:
    cc = f"\\textbf{{CC:}} {_latex_escape(item.cc)} \\\\\n" if item.cc else ""
    return f"""\
\\documentclass[11pt]{{article}}
\\usepackage[margin=1in]{{geometry}}
\\usepackage{{parskip}}
\\usepackage{{xcolor}}
\\begin{{document}}

\\colorbox{{gray!15}}{{\\parbox{{\\dimexpr\\textwidth-2\\fboxsep}}{{%
\\textbf{{From:}} {_latex_escape(item.from_address)} \\\\
\\textbf{{To:}} {_latex_escape(item.to_address)} \\\\
{cc}\\textbf{{Date:}} {_latex_escape(item.date)} \\\\
\\textbf{{Subject:}} {_latex_escape(item.subject)}}}}}

\\bigskip

{_latex_escape(item.body_text)}

\\end{{document}}"""


def _email_html(item: Email) -> str:
    cc = f'<p><strong>CC:</strong> {_html_escape(item.cc)}</p>' if item.cc else ""
    return f"""\
<!DOCTYPE html>
<html lang="en">
<head><meta charset="UTF-8">
<title>{_html_escape(item.subject)}</title>
<style>
  body {{ font-family: 'Courier New', monospace; max-width: 800px; margin: 40px auto; padding: 0 20px; }}
  .header {{ background: #f0f0f0; padding: 12px; margin-bottom: 1em; border: 1px solid #ccc; }}
  .header p {{ margin: 3px 0; }}
</style>
</head>
<body>
<div class="header">
  <p><strong>From:</strong> {_html_escape(item.from_address)}</p>
  <p><strong>To:</strong> {_html_escape(item.to_address)}</p>
  {cc}
  <p><strong>Date:</strong> {_html_escape(item.date)}</p>
  <p><strong>Subject:</strong> {_html_escape(item.subject)}</p>
</div>
<div style="white-space: pre-wrap; line-height: 1.5;">{_html_escape(item.body_text)}</div>
</body>
</html>"""


# ===========================================================================
# Person of Interest Form (with mugshot photo)
# ===========================================================================


def _poi_full_name(item: PersonOfInterestForm) -> str:
    return " ".join(filter(None, [item.name, item.middle_name, item.last_name]))


def _poi_address(item: PersonOfInterestForm) -> str:
    return ", ".join(filter(None, [item.street_address, item.city, item.postal_code, item.country]))


def _poi_typst(item: PersonOfInterestForm, portrait: str | None, hw_font: str) -> str:
    full_name = _poi_full_name(item)

    portrait_block = ""
    if portrait:
        portrait_block = f"""
#place(top + right, dx: 0cm, dy: -0.5cm)[
  #box(stroke: 0.5pt, inset: 2pt)[#image("{portrait}", width: 3cm)]
]
"""

    return f"""\
#set page(margin: (x: 2cm, y: 2cm))
#set text(font: "New Computer Modern", size: 9pt)

#text(size: 16pt, weight: "bold")[Person of Interest (PoI)]
{portrait_block}
#v(0.3em)

*Personal Information*

#table(
  columns: (1fr, 1fr, 1fr),
  stroke: 0.5pt,
  inset: 6pt,
  [*First Name* #linebreak() #text(font: "{hw_font}", size: 13pt)[{item.name}]],
  [*Middle Name* #linebreak() #text(font: "{hw_font}", size: 13pt)[{item.middle_name or ""}]],
  [*Last Name* #linebreak() #text(font: "{hw_font}", size: 13pt)[{item.last_name}]],
  [*Alias / Maiden Name / Prior Names* #linebreak() #text(font: "{hw_font}", size: 13pt)[{item.nickname or "N/A"}]],
  [*Date of Birth* #linebreak() #text(font: "{hw_font}", size: 13pt)[{item.date_of_birth}]],
  [*Country of Birth* #linebreak() #text(font: "{hw_font}", size: 13pt)[{item.country_of_birth or "N/A"}]],
  [*Nationality* #linebreak() #text(font: "{hw_font}", size: 13pt)[{item.nationality or "N/A"}]],
  [*National Identity Number* #linebreak() #text(font: "{hw_font}", size: 13pt)[{item.id_number or "N/A"}]],
  [*Occupation* #linebreak() #text(font: "{hw_font}", size: 13pt)[{item.occupation or "N/A"}]],
)

*Contact Information*

#table(
  columns: (1fr, 2fr),
  stroke: 0.5pt,
  inset: 6pt,
  [*Phone Number (Country Code)* #linebreak() #text(font: "{hw_font}", size: 13pt)[{item.phone_country_code}]],
  [*Phone Number* #linebreak() #text(font: "{hw_font}", size: 13pt)[{item.phone_number}]],
)

#table(
  columns: (1fr, 1fr, 0.5fr, 1fr),
  stroke: 0.5pt,
  inset: 6pt,
  [*Home Address* #linebreak() #text(font: "{hw_font}", size: 13pt)[{item.street_address}]],
  [*City* #linebreak() #text(font: "{hw_font}", size: 13pt)[{item.city}]],
  [*Zip Code* #linebreak() #text(font: "{hw_font}", size: 13pt)[{item.postal_code}]],
  [*Country* #linebreak() #text(font: "{hw_font}", size: 13pt)[{item.country}]],
)

*Physical Description*

#table(
  columns: (1fr, 1fr),
  stroke: 0.5pt,
  inset: 6pt,
  [*Height (cm)* #linebreak() #text(font: "{hw_font}", size: 13pt)[{item.height_cm or "N/A"}]],
  [*Weight (kg)* #linebreak() #text(font: "{hw_font}", size: 13pt)[{item.weight_kg or "N/A"}]],
)

#table(
  columns: (1fr, 1fr, 1fr),
  stroke: 0.5pt,
  inset: 6pt,
  [*Eye Color* #linebreak() #text(font: "{hw_font}", size: 13pt)[{item.eye_color or "N/A"}]],
  [*Hair Color* #linebreak() #text(font: "{hw_font}", size: 13pt)[{item.hair_color or "N/A"}]],
  [*Shoe Size (EU/cm)* #linebreak() #text(font: "{hw_font}", size: 13pt)[{item.shoe_size_eu or "N/A"}]],
)

*Additional Information*

#table(
  columns: (1fr, 1fr),
  stroke: 0.5pt,
  inset: 6pt,
  [*Vehicle Ownership (License plate)* #linebreak() #text(font: "{hw_font}", size: 13pt)[{item.vehicle_plates or "N/A"}]],
  [*Employer name* #linebreak() #text(font: "{hw_font}", size: 13pt)[{item.employer or "N/A"}]],
  [*Prior arrests (YES/NO)* #linebreak() #text(font: "{hw_font}", size: 13pt)[{"Yes" if item.prior_arrests else "No"}]],
  [*Criminal record (YES/NO)* #linebreak() #text(font: "{hw_font}", size: 13pt)[{"Yes" if item.prior_convictions else "No"}]],
)

#v(0.5em)
#text(size: 8pt)[I hereby confirm that all the information provided in this form is true and accurate to the best of my knowledge. I understand that providing false or misleading information may have legal consequences.]

*Signature*

#text(font: "{hw_font}", size: 16pt)[{item.signature or full_name}]

#line(length: 50%, stroke: (dash: "dashed"))
"""


def _poi_latex(item: PersonOfInterestForm, portrait: str | None) -> str:
    full_name = _poi_full_name(item)
    graphicx = "\\usepackage{graphicx}\n" if portrait else ""

    portrait_block = ""
    if portrait:
        portrait_block = (
            f"\\begin{{wrapfigure}}{{r}}{{3cm}}\n"
            f"\\includegraphics[width=3cm]{{{portrait}}}\n"
            f"\\end{{wrapfigure}}\n"
        )

    return f"""\
\\documentclass[11pt]{{article}}
\\usepackage[margin=1in]{{geometry}}
\\usepackage{{parskip}}
\\usepackage{{array}}
\\usepackage{{wrapfig}}
{graphicx}\\begin{{document}}

\\textbf{{\\Large Person of Interest (PoI)}}

{portrait_block}
\\textbf{{Personal Information}}\\\\[0.5em]
\\begin{{tabular}}{{|p{{4.5cm}}|p{{4.5cm}}|p{{4.5cm}}|}}
\\hline
\\textbf{{First Name}} & \\textbf{{Middle Name}} & \\textbf{{Last Name}} \\\\
{_latex_escape(item.name)} & {_latex_escape(item.middle_name or "")} & {_latex_escape(item.last_name)} \\\\\\hline
\\textbf{{Alias}} & \\textbf{{Date of Birth}} & \\textbf{{Country of Birth}} \\\\
{_latex_escape(item.nickname or "N/A")} & {_latex_escape(item.date_of_birth)} & {_latex_escape(item.country_of_birth or "N/A")} \\\\\\hline
\\textbf{{Nationality}} & \\textbf{{ID Number}} & \\textbf{{Occupation}} \\\\
{_latex_escape(item.nationality or "N/A")} & {_latex_escape(item.id_number or "N/A")} & {_latex_escape(item.occupation or "N/A")} \\\\\\hline
\\end{{tabular}}

\\bigskip
\\textbf{{Contact Information}}\\\\[0.5em]
\\begin{{tabular}}{{|p{{4.5cm}}|p{{9cm}}|}}
\\hline
\\textbf{{Phone (Country Code)}} & \\textbf{{Phone Number}} \\\\
{_latex_escape(item.phone_country_code)} & {_latex_escape(item.phone_number)} \\\\\\hline
\\end{{tabular}}

\\begin{{tabular}}{{|p{{4.5cm}}|p{{3cm}}|p{{1.5cm}}|p{{3cm}}|}}
\\hline
\\textbf{{Home Address}} & \\textbf{{City}} & \\textbf{{Zip}} & \\textbf{{Country}} \\\\
{_latex_escape(item.street_address)} & {_latex_escape(item.city)} & {_latex_escape(item.postal_code)} & {_latex_escape(item.country)} \\\\\\hline
\\end{{tabular}}

\\bigskip
\\textbf{{Physical Description}}\\\\[0.5em]
\\begin{{tabular}}{{|p{{4.5cm}}|p{{4.5cm}}|p{{4.5cm}}|}}
\\hline
\\textbf{{Height (cm)}} & \\textbf{{Weight (kg)}} & \\textbf{{Shoe Size (EU)}} \\\\
{_latex_escape(item.height_cm or "N/A")} & {_latex_escape(item.weight_kg or "N/A")} & {_latex_escape(item.shoe_size_eu or "N/A")} \\\\\\hline
\\textbf{{Eye Color}} & \\textbf{{Hair Color}} & \\\\
{_latex_escape(item.eye_color or "N/A")} & {_latex_escape(item.hair_color or "N/A")} & \\\\\\hline
\\end{{tabular}}

\\bigskip
\\textbf{{Additional Information}}\\\\[0.5em]
\\begin{{tabular}}{{|p{{7cm}}|p{{6.5cm}}|}}
\\hline
\\textbf{{Vehicle (License plate)}} & \\textbf{{Employer}} \\\\
{_latex_escape(item.vehicle_plates or "N/A")} & {_latex_escape(item.employer or "N/A")} \\\\\\hline
\\textbf{{Prior arrests (YES/NO)}} & \\textbf{{Criminal record (YES/NO)}} \\\\
{"Yes" if item.prior_arrests else "No"} & {"Yes" if item.prior_convictions else "No"} \\\\\\hline
\\end{{tabular}}

\\bigskip
\\textbf{{Signature:}} \\textit{{{_latex_escape(item.signature or full_name)}}}

\\end{{document}}"""


def _poi_html(item: PersonOfInterestForm, portrait: str | None, hw_font: str) -> str:
    full_name = _poi_full_name(item)

    photo_block = ""
    if portrait:
        photo_block = (
            f'<img src="{portrait}" '
            f'style="width: 120px; border: 1px solid #ccc; float: right; margin-left: 1em;">'
        )

    return f"""\
<!DOCTYPE html>
<html lang="en">
<head><meta charset="UTF-8">
<title>POI Form</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family={hw_font.replace(' ', '+')}&display=swap" rel="stylesheet">
<style>
  body {{ font-family: Arial, sans-serif; max-width: 800px; margin: 40px auto; padding: 0 20px; font-size: 10pt; }}
  h1 {{ font-size: 1.4em; margin-bottom: 0.3em; }}
  h2 {{ font-size: 0.9em; font-weight: bold; margin: 0.8em 0 0.3em; }}
  table {{ width: 100%; border-collapse: collapse; margin-bottom: 0.3em; }}
  td {{ border: 1px solid #999; padding: 4px 8px; vertical-align: top; }}
  .label {{ font-weight: bold; font-size: 0.85em; display: block; }}
  .val {{ font-family: '{hw_font}', cursive; font-size: 1.3em; }}
  .sig {{ font-family: '{hw_font}', cursive; font-size: 1.5em; }}
</style>
</head>
<body>
{photo_block}
<h1>Person of Interest (PoI)</h1>

<h2>Personal Information</h2>
<table>
  <tr>
    <td><span class="label">First Name</span><span class="val">{_html_escape(item.name)}</span></td>
    <td><span class="label">Middle Name</span><span class="val">{_html_escape(item.middle_name or "")}</span></td>
    <td><span class="label">Last Name</span><span class="val">{_html_escape(item.last_name)}</span></td>
  </tr>
  <tr>
    <td><span class="label">Alias / Maiden Name</span><span class="val">{_html_escape(item.nickname or "N/A")}</span></td>
    <td><span class="label">Date of Birth</span><span class="val">{_html_escape(item.date_of_birth)}</span></td>
    <td><span class="label">Country of Birth</span><span class="val">{_html_escape(item.country_of_birth or "N/A")}</span></td>
  </tr>
  <tr>
    <td><span class="label">Nationality</span><span class="val">{_html_escape(item.nationality or "N/A")}</span></td>
    <td><span class="label">National Identity Number</span><span class="val">{_html_escape(item.id_number or "N/A")}</span></td>
    <td><span class="label">Occupation</span><span class="val">{_html_escape(item.occupation or "N/A")}</span></td>
  </tr>
</table>

<h2>Contact Information</h2>
<table>
  <tr>
    <td style="width: 30%;"><span class="label">Phone Number (Country Code)</span><span class="val">{_html_escape(item.phone_country_code)}</span></td>
    <td><span class="label">Phone Number</span><span class="val">{_html_escape(item.phone_number)}</span></td>
  </tr>
</table>
<table>
  <tr>
    <td><span class="label">Home Address</span><span class="val">{_html_escape(item.street_address)}</span></td>
    <td><span class="label">City</span><span class="val">{_html_escape(item.city)}</span></td>
    <td style="width: 12%;"><span class="label">Zip Code</span><span class="val">{_html_escape(item.postal_code)}</span></td>
    <td><span class="label">Country</span><span class="val">{_html_escape(item.country)}</span></td>
  </tr>
</table>

<h2>Physical Description</h2>
<table>
  <tr>
    <td><span class="label">Height (cm)</span><span class="val">{_html_escape(item.height_cm or "N/A")}</span></td>
    <td><span class="label">Weight (kg)</span><span class="val">{_html_escape(item.weight_kg or "N/A")}</span></td>
  </tr>
  <tr>
    <td><span class="label">Eye Color</span><span class="val">{_html_escape(item.eye_color or "N/A")}</span></td>
    <td><span class="label">Hair Color</span><span class="val">{_html_escape(item.hair_color or "N/A")}</span></td>
    <td><span class="label">Shoe Size (EU/cm)</span><span class="val">{_html_escape(item.shoe_size_eu or "N/A")}</span></td>
  </tr>
</table>

<h2>Additional Information</h2>
<table>
  <tr>
    <td><span class="label">Vehicle Ownership (License plate)</span><span class="val">{_html_escape(item.vehicle_plates or "N/A")}</span></td>
    <td><span class="label">Employer name</span><span class="val">{_html_escape(item.employer or "N/A")}</span></td>
  </tr>
  <tr>
    <td><span class="label">Prior arrests (YES/NO)</span><span class="val">{"Yes" if item.prior_arrests else "No"}</span></td>
    <td><span class="label">Criminal record (YES/NO)</span><span class="val">{"Yes" if item.prior_convictions else "No"}</span></td>
  </tr>
</table>

<p style="font-size: 0.8em; margin-top: 1em;">I hereby confirm that all the information provided in this form is true and accurate to the best of my knowledge. I understand that providing false or misleading information may have legal consequences.</p>

<p><strong>Signature</strong></p>
<p class="sig">{_html_escape(item.signature or full_name)}</p>
<hr style="width: 50%; border-style: dashed; margin-left: 0;">
</body>
</html>"""


# ===========================================================================
# Phone Log
# ===========================================================================


def _phone_typst(item: PhoneLog) -> str:
    rows = "\n".join(
        f"  [{e.timestamp}], [{_direction_icon(e.direction)} {e.direction}], "
        f"[{e.other_party}], [{e.duration or '--'}],"
        for e in item.entries
    )
    return f"""\
#set page(margin: (x: 2cm, y: 2cm))
#set text(font: "New Computer Modern", size: 10pt)

#align(center)[#text(size: 14pt, weight: "bold")[PHONE CALL LOG]]

#v(0.5em)

#table(
  columns: (auto, 1fr),
  stroke: none,
  [*Owner:*], [{item.owner_name}],
  [*Phone Number:*], [{item.phone_number}],
)

#v(0.5em)
#line(length: 100%)
#v(0.5em)

#table(
  columns: (auto, auto, 1fr, auto),
  stroke: 0.5pt,
  [*Timestamp*], [*Direction*], [*Other Party*], [*Duration*],
{rows}
)
"""


def _phone_latex(item: PhoneLog) -> str:
    dir_latex = {"incoming": r"$\leftarrow$", "outgoing": r"$\rightarrow$", "missed": r"$\times$"}
    rows = "\n".join(
        f"  {_latex_escape(e.timestamp)} & {dir_latex.get(e.direction, '?')} {_latex_escape(e.direction)} & "
        f"{_latex_escape(e.other_party)} & {_latex_escape(e.duration or '---')} \\\\"
        for e in item.entries
    )
    return f"""\
\\documentclass[11pt]{{article}}
\\usepackage[margin=1in]{{geometry}}
\\usepackage{{parskip}}
\\usepackage{{longtable}}
\\usepackage{{array}}
\\begin{{document}}

\\begin{{center}}
\\textbf{{\\Large PHONE CALL LOG}}
\\end{{center}}

\\begin{{tabular}}{{@{{}}ll@{{}}}}
\\textbf{{Owner:}} & {_latex_escape(item.owner_name)} \\\\
\\textbf{{Phone Number:}} & {_latex_escape(item.phone_number)} \\\\
\\end{{tabular}}

\\bigskip\\hrule\\bigskip

\\begin{{longtable}}{{|l|l|l|l|}}
\\hline
\\textbf{{Timestamp}} & \\textbf{{Direction}} & \\textbf{{Other Party}} & \\textbf{{Duration}} \\\\\\hline
\\endhead
{rows}
\\hline
\\end{{longtable}}

\\end{{document}}"""


def _phone_html(item: PhoneLog) -> str:
    rows = "\n".join(
        f"<tr><td>{_html_escape(e.timestamp)}</td>"
        f"<td>{_direction_icon(e.direction)} {_html_escape(e.direction)}</td>"
        f"<td>{_html_escape(e.other_party)}</td>"
        f'<td>{_html_escape(e.duration or "\u2014")}</td></tr>'
        for e in item.entries
    )
    return f"""\
<!DOCTYPE html>
<html lang="en">
<head><meta charset="UTF-8">
<title>Phone Log</title>
<style>
  body {{ font-family: Arial, sans-serif; max-width: 800px; margin: 40px auto; padding: 0 20px; }}
  h1 {{ text-align: center; font-size: 1.3em; }}
  .meta p {{ margin: 2px 0; }}
  table {{ width: 100%; border-collapse: collapse; margin-top: 1em; }}
  th, td {{ border: 1px solid #999; padding: 6px 10px; text-align: left; }}
  th {{ background: #f5f5f5; }}
  hr {{ border: none; border-top: 1px solid #999; margin: 1em 0; }}
</style>
</head>
<body>
<h1>PHONE CALL LOG</h1>
<div class="meta">
  <p><strong>Owner:</strong> {_html_escape(item.owner_name)}</p>
  <p><strong>Phone Number:</strong> {_html_escape(item.phone_number)}</p>
</div>
<hr>
<table>
  <tr><th>Timestamp</th><th>Direction</th><th>Other Party</th><th>Duration</th></tr>
{rows}
</table>
</body>
</html>"""


# ===========================================================================
# SMS Log
# ===========================================================================


def _sms_typst(item: SmsLog) -> str:
    msgs: list[str] = []
    for msg in item.messages:
        align = "right" if msg.direction == "outgoing" else "left"
        bg = "#e1f0ff" if msg.direction == "outgoing" else "#f0f0f0"
        label = item.owner_name if msg.direction == "outgoing" else item.other_party
        msgs.append(
            f'#align({align})[\n'
            f'  #box(fill: rgb("{bg}"), radius: 6pt, inset: 8pt, width: 70%)[\n'
            f'    #text(size: 8pt, fill: rgb("#666"))[{msg.timestamp} -- {label}] \\\n'
            f"    {msg.text}\n"
            f"  ]\n]\n#v(0.3em)"
        )
    chat = "\n".join(msgs)
    return f"""\
#set page(margin: (x: 2cm, y: 2cm))
#set text(font: "New Computer Modern", size: 10pt)

#align(center)[#text(size: 14pt, weight: "bold")[SMS MESSAGE LOG]]

#v(0.5em)

#table(
  columns: (auto, 1fr),
  stroke: none,
  [*Owner:*], [{item.owner_name}],
  [*Phone Number:*], [{item.phone_number}],
  [*Conversation with:*], [{item.other_party}],
)

#v(0.5em)
#line(length: 100%)
#v(0.5em)

{chat}
"""


def _sms_latex(item: SmsLog) -> str:
    msgs: list[str] = []
    for msg in item.messages:
        align = "flushright" if msg.direction == "outgoing" else "flushleft"
        label = _latex_escape(item.owner_name if msg.direction == "outgoing" else item.other_party)
        msgs.append(
            f"\\begin{{{align}}}\n"
            f"\\fbox{{\\parbox{{0.7\\textwidth}}{{\n"
            f"  {{\\scriptsize {_latex_escape(msg.timestamp)} -- {label}}} \\\\\n"
            f"  {_latex_escape(msg.text)}\n"
            f"}}}}\n"
            f"\\end{{{align}}}\n"
            f"\\smallskip"
        )
    chat = "\n".join(msgs)
    return f"""\
\\documentclass[11pt]{{article}}
\\usepackage[margin=1in]{{geometry}}
\\usepackage{{parskip}}
\\begin{{document}}

\\begin{{center}}
\\textbf{{\\Large SMS MESSAGE LOG}}
\\end{{center}}

\\begin{{tabular}}{{@{{}}ll@{{}}}}
\\textbf{{Owner:}} & {_latex_escape(item.owner_name)} \\\\
\\textbf{{Phone Number:}} & {_latex_escape(item.phone_number)} \\\\
\\textbf{{Conversation with:}} & {_latex_escape(item.other_party)} \\\\
\\end{{tabular}}

\\bigskip\\hrule\\bigskip

{chat}

\\end{{document}}"""


def _sms_html(item: SmsLog) -> str:
    msgs: list[str] = []
    for msg in item.messages:
        bg = "#e1f0ff" if msg.direction == "outgoing" else "#f0f0f0"
        label = _html_escape(item.owner_name if msg.direction == "outgoing" else item.other_party)
        ml = "auto" if msg.direction == "outgoing" else "0"
        mr = "0" if msg.direction == "outgoing" else "auto"
        msgs.append(
            f'<div style="width: 70%; margin-left: {ml}; margin-right: {mr}; '
            f"background: {bg}; padding: 8px 12px; border-radius: 8px; margin-bottom: 8px;\">"
            f'<div style="font-size: 0.75em; color: #666;">{_html_escape(msg.timestamp)} &mdash; {label}</div>'
            f"<div>{_html_escape(msg.text)}</div></div>"
        )
    chat = "\n".join(msgs)
    return f"""\
<!DOCTYPE html>
<html lang="en">
<head><meta charset="UTF-8">
<title>SMS Log</title>
<style>
  body {{ font-family: Arial, sans-serif; max-width: 600px; margin: 40px auto; padding: 0 20px; }}
  h1 {{ text-align: center; font-size: 1.3em; }}
  .meta p {{ margin: 2px 0; }}
  hr {{ border: none; border-top: 1px solid #999; margin: 1em 0; }}
</style>
</head>
<body>
<h1>SMS MESSAGE LOG</h1>
<div class="meta">
  <p><strong>Owner:</strong> {_html_escape(item.owner_name)}</p>
  <p><strong>Phone Number:</strong> {_html_escape(item.phone_number)}</p>
  <p><strong>Conversation with:</strong> {_html_escape(item.other_party)}</p>
</div>
<hr>
{chat}
</body>
</html>"""


# ===========================================================================
# Handwritten Note
# ===========================================================================


def _handwritten_typst(item: HandwrittenNote, font: str) -> str:
    return f"""\
#set page(margin: (x: 2.5cm, y: 2.5cm), fill: rgb("#fffef5"))
#set text(font: "{font}", size: 14pt)
#set par(leading: 1em)

{item.content}
"""


def _handwritten_html(item: HandwrittenNote, font: str) -> str:
    return f"""\
<!DOCTYPE html>
<html lang="en">
<head><meta charset="UTF-8">
<title>Note</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family={font.replace(' ', '+')}&display=swap" rel="stylesheet">
<style>
  body {{
    font-family: '{font}', cursive;
    font-size: 18px;
    max-width: 600px;
    margin: 60px auto;
    padding: 40px;
    background: #fffef5;
    line-height: 2;
    min-height: 80vh;
  }}
</style>
</head>
<body>
<div style="white-space: pre-wrap;">{_html_escape(item.content)}</div>
</body>
</html>"""


# ===========================================================================
# Instagram Post
# ===========================================================================


def _instagram_typst(item: InstagramPost, image: str | None) -> str:
    image_block = f'#image("{image}", width: 100%)\n' if image else ""
    return f"""\
#set page(margin: 0pt, width: 14cm, height: auto)
#set text(font: "New Computer Modern", size: 10pt)

#rect(fill: white, width: 100%, inset: 0pt)[
  #box(width: 100%, inset: (x: 12pt, y: 8pt))[
    #text(weight: "bold")[{item.username}]
  ]
  {image_block}
  #box(width: 100%, inset: (x: 12pt, y: 8pt))[
    #text(fill: rgb("#333"))[\\u{{2764}} {item.likes} likes]
    #v(0.2em)
    #text(weight: "bold")[{item.username}] {item.caption}
    #v(0.2em)
    #text(size: 8pt, fill: rgb("#999"))[{item.date}]
  ]
]
"""


def _instagram_html(item: InstagramPost, image: str | None) -> str:
    image_block = f'<img src="{image}" style="width: 100%; display: block;">' if image else ""
    return f"""\
<!DOCTYPE html>
<html lang="en">
<head><meta charset="UTF-8">
<title>Instagram Post</title>
<style>
  body {{ font-family: -apple-system, 'Segoe UI', Arial, sans-serif; margin: 40px auto; max-width: 500px; padding: 0; background: #fafafa; }}
  .post {{ background: white; border: 1px solid #dbdbdb; border-radius: 3px; }}
  .header {{ padding: 10px 14px; font-weight: bold; font-size: 14px; }}
  .caption {{ padding: 10px 14px; font-size: 14px; line-height: 1.4; }}
  .caption b {{ font-weight: 600; }}
  .likes {{ padding: 6px 14px; font-weight: 600; font-size: 14px; }}
  .date {{ padding: 4px 14px 10px; font-size: 10px; color: #999; text-transform: uppercase; }}
</style>
</head>
<body>
<div class="post">
  <div class="header">{_html_escape(item.username)}</div>
  {image_block}
  <div class="likes">\u2764\ufe0f {item.likes} likes</div>
  <div class="caption"><b>{_html_escape(item.username)}</b> {_html_escape(item.caption)}</div>
  <div class="date">{_html_escape(item.date)}</div>
</div>
</body>
</html>"""


# ===========================================================================
# Facebook Post
# ===========================================================================


def _facebook_typst(item: FacebookPost) -> str:
    comments = ""
    if item.comments:
        comment_lines = "\n".join(
            f"  #box(inset: (left: 8pt, y: 4pt))[#text(size: 9pt)[{c}]]"
            for c in item.comments
        )
        comments = f"\n  #line(length: 100%, stroke: 0.3pt)\n{comment_lines}"
    return f"""\
#set page(margin: (x: 2cm, y: 2cm))
#set text(font: "New Computer Modern", size: 10pt)

#rect(fill: white, stroke: 0.5pt + rgb("#ddd"), width: 100%, radius: 4pt, inset: 12pt)[
  #text(weight: "bold", size: 11pt)[{item.author_name}]
  #h(1fr)
  #text(size: 8pt, fill: rgb("#999"))[{item.date}]

  #v(0.5em)

  {item.content}

  #v(0.5em)
  #text(fill: rgb("#666"), size: 9pt)[\\u{{1F44D}} {item.likes}]{comments}
]
"""


def _facebook_html(item: FacebookPost) -> str:
    comments_html = ""
    if item.comments:
        c_items = "\n".join(
            f'<div style="padding: 6px 0; font-size: 13px; border-top: 1px solid #eee;">{_html_escape(c)}</div>'
            for c in item.comments
        )
        comments_html = f'<div style="margin-top: 8px;">{c_items}</div>'
    return f"""\
<!DOCTYPE html>
<html lang="en">
<head><meta charset="UTF-8">
<title>Facebook Post</title>
<style>
  body {{ font-family: -apple-system, 'Segoe UI', Arial, sans-serif; margin: 40px auto; max-width: 550px; background: #f0f2f5; padding: 20px; }}
  .post {{ background: white; border-radius: 8px; padding: 16px; box-shadow: 0 1px 2px rgba(0,0,0,0.1); }}
  .author {{ font-weight: 600; font-size: 15px; }}
  .date {{ font-size: 12px; color: #999; }}
  .content {{ margin: 10px 0; font-size: 15px; line-height: 1.4; white-space: pre-wrap; }}
  .likes {{ font-size: 13px; color: #666; }}
</style>
</head>
<body>
<div class="post">
  <div><span class="author">{_html_escape(item.author_name)}</span></div>
  <div class="date">{_html_escape(item.date)}</div>
  <div class="content">{_html_escape(item.content)}</div>
  <div class="likes">\U0001F44D {item.likes}</div>
  {comments_html}
</div>
</body>
</html>"""


# ===========================================================================
# Helpers
# ===========================================================================


def _direction_icon(direction: str) -> str:
    return {"incoming": "\u2190", "outgoing": "\u2192", "missed": "\u2717"}.get(direction, "?")


def _find_portrait(case: Case, suspect: object, dest_folder: Path) -> str | None:
    """Find and copy a suspect's portrait image to dest_folder. Returns filename or None."""
    img_dir = images_dir(case.id)
    if not img_dir.exists():
        return None

    # Try the stored filename first
    name_attr = getattr(suspect, "portrait_filename", None)
    if name_attr:
        src = img_dir / name_attr
        if src.exists():
            shutil.copy2(src, dest_folder / name_attr)
            return name_attr

    # Fallback: scan images dir for a portrait matching the suspect's name
    suspect_name = getattr(suspect, "name", "")
    slug = suspect_name.lower().replace(" ", "-")
    for f in img_dir.iterdir():
        if f.suffix == ".png" and "portrait" in f.stem.lower() and slug in f.stem.lower():
            shutil.copy2(f, dest_folder / f.name)
            return f.name

    return None


def _latex_escape(text: str) -> str:
    """Escape characters special to LaTeX."""
    for char, repl in {
        "&": r"\&",
        "%": r"\%",
        "$": r"\$",
        "#": r"\#",
        "_": r"\_",
        "{": r"\{",
        "}": r"\}",
        "~": r"\textasciitilde{}",
        "^": r"\textasciicircum{}",
    }.items():
        text = text.replace(char, repl)
    return text


def _html_escape(text: str) -> str:
    """Escape HTML special characters."""
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )
