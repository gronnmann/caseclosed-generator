"""Export evidence to Typst, LaTeX, and HTML, compiled to PDF."""

import shutil
import subprocess
from pathlib import Path

from rich.console import Console

from caseclosed.models.case import Case
from caseclosed.models.evidence import (
    Email,
    EvidencePlanItem,
    InterrogationReport,
    Letter,
    PersonOfInterestForm,
    PhoneLog,
    RawText,
    SmsLog,
)
from caseclosed.persistence import images_dir

console = Console()


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

        plan = plan_map.get(item.plan_id)
        ep = plan.introduced_in_episode if plan else 0
        eid = item.plan_id
        folder = _src_dir(out, eid)

        # Copy suspect portrait into source dir for POI forms
        portrait_file: str | None = None
        if isinstance(item, PersonOfInterestForm) and plan and plan.suspect_name:
            suspect = next((s for s in case.suspects if s.name == plan.suspect_name), None)
            if suspect:
                portrait_file = _find_portrait(case, suspect, folder)

        formats = _formats_for(item, portrait_file)

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
        console.print(f"[dim]({skip_count} image evidence items skipped)[/dim]")
    return out


# ---------------------------------------------------------------------------
# Format dispatch
# ---------------------------------------------------------------------------


def _formats_for(
    item: object,
    portrait_file: str | None = None,
) -> dict[str, tuple[str, str]]:
    """Return {format_key: (source_filename, content)} for each output format."""
    match item:
        case InterrogationReport():
            return {
                "typst": ("doc.typ", _interrogation_typst(item)),
                "latex": ("doc.tex", _interrogation_latex(item)),
                "html": ("doc.html", _interrogation_html(item)),
            }
        case Letter():
            return {
                "typst": ("doc.typ", _letter_typst(item)),
                "latex": ("doc.tex", _letter_latex(item)),
                "html": ("doc.html", _letter_html(item)),
            }
        case RawText():
            return {
                "typst": ("doc.typ", item.text_typst or _rawtext_typst(item)),
                "latex": ("doc.tex", item.text_latex or _rawtext_latex(item)),
                "html": ("doc.html", item.text_html or _rawtext_html(item)),
            }
        case Email():
            return {
                "typst": ("doc.typ", item.text_typst or _email_typst(item)),
                "latex": ("doc.tex", _email_latex(item)),
                "html": ("doc.html", item.text_html or _email_html(item)),
            }
        case PersonOfInterestForm():
            return {
                "typst": ("doc.typ", _poi_typst(item, portrait_file)),
                "latex": ("doc.tex", _poi_latex(item, portrait_file)),
                "html": ("doc.html", _poi_html(item, portrait_file)),
            }
        case PhoneLog():
            return {
                "typst": ("doc.typ", _phone_typst(item)),
                "latex": ("doc.tex", _phone_latex(item)),
                "html": ("doc.html", _phone_html(item)),
            }
        case SmsLog():
            return {
                "typst": ("doc.typ", _sms_typst(item)),
                "latex": ("doc.tex", _sms_latex(item)),
                "html": ("doc.html", _sms_html(item)),
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

#v(1em)
#line(length: 100%)
#align(center)[#text(size: 9pt)[_End of transcript_]]
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


def _letter_typst(item: Letter) -> str:
    body = item.text_typst or item.body_text
    return f"""\
#set page(margin: (x: 2.5cm, y: 2.5cm))
#set text(font: "New Computer Modern", size: 11pt)
#set par(justify: true)

#align(right)[{item.date or ""}]
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


def _letter_html(item: Letter) -> str:
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
<p style="text-align: right;">{_html_escape(item.date or "")}</p>
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


def _poi_typst(item: PersonOfInterestForm, portrait: str | None) -> str:
    full_name = _poi_full_name(item)
    address = _poi_address(item)

    personal_rows = f"""\
      [*Full Name*], [{full_name}],
      [*Nickname*], [{item.nickname or "N/A"}],
      [*Date of Birth*], [{item.date_of_birth}],
      [*Nationality*], [{item.nationality or "N/A"}],
      [*ID Number*], [{item.id_number or "N/A"}],
      [*Occupation*], [{item.occupation or "N/A"}],"""

    if portrait:
        personal_section = f"""\
#grid(
  columns: (1fr, 3.5cm),
  column-gutter: 1em,
  [
    #table(
      columns: (4.5cm, 1fr),
      stroke: 0.5pt,
{personal_rows}
    )
  ],
  [#image("{portrait}", width: 100%)],
)"""
    else:
        personal_section = f"""\
#table(
  columns: (4.5cm, 1fr),
  stroke: 0.5pt,
{personal_rows}
)"""

    return f"""\
#set page(margin: (x: 2cm, y: 2cm))
#set text(font: "New Computer Modern", size: 10pt)

#align(center)[
  #text(size: 14pt, weight: "bold")[PERSON OF INTEREST -- INFORMATION FORM]
]

#v(0.5em)
#line(length: 100%)
#v(0.5em)

#text(size: 11pt, weight: "bold")[PERSONAL DETAILS]

{personal_section}

#v(0.5em)
#text(size: 11pt, weight: "bold")[CONTACT INFORMATION]

#table(
  columns: (4.5cm, 1fr),
  stroke: 0.5pt,
  [*Phone*], [{item.phone_country_code} {item.phone_number}],
  [*Address*], [{address}],
)

#v(0.5em)
#text(size: 11pt, weight: "bold")[PHYSICAL DESCRIPTION]

#table(
  columns: (4.5cm, 1fr),
  stroke: 0.5pt,
  [*Height (cm)*], [{item.height_cm or "N/A"}],
  [*Weight (kg)*], [{item.weight_kg or "N/A"}],
  [*Eye Color*], [{item.eye_color or "N/A"}],
  [*Hair Color*], [{item.hair_color or "N/A"}],
  [*Shoe Size (EU)*], [{item.shoe_size_eu or "N/A"}],
)

#v(0.5em)
#text(size: 11pt, weight: "bold")[ADDITIONAL INFORMATION]

#table(
  columns: (4.5cm, 1fr),
  stroke: 0.5pt,
  [*Vehicle Plates*], [{item.vehicle_plates or "N/A"}],
  [*Employer*], [{item.employer or "N/A"}],
  [*Prior Arrests*], [{"Yes" if item.prior_arrests else "No"}],
  [*Prior Convictions*], [{"Yes" if item.prior_convictions else "No"}],
)

#v(1.5em)
#line(length: 100%)
#table(
  columns: (1fr, 1fr),
  stroke: none,
  [*Signature:* _{item.signature or ""}_], [*Date:*],
)
"""


def _poi_latex(item: PersonOfInterestForm, portrait: str | None) -> str:
    full_name = _poi_full_name(item)
    address = _poi_address(item)
    graphicx = "\\usepackage{graphicx}\n" if portrait else ""

    personal_table = f"""\
\\begin{{tabular}}{{|l|l|}}
\\hline
\\textbf{{Full Name}} & {_latex_escape(full_name)} \\\\\\hline
\\textbf{{Nickname}} & {_latex_escape(item.nickname or "N/A")} \\\\\\hline
\\textbf{{Date of Birth}} & {_latex_escape(item.date_of_birth)} \\\\\\hline
\\textbf{{Nationality}} & {_latex_escape(item.nationality or "N/A")} \\\\\\hline
\\textbf{{ID Number}} & {_latex_escape(item.id_number or "N/A")} \\\\\\hline
\\textbf{{Occupation}} & {_latex_escape(item.occupation or "N/A")} \\\\\\hline
\\end{{tabular}}"""

    if portrait:
        personal_section = (
            f"\\begin{{minipage}}{{0.6\\textwidth}}\n{personal_table}\n\\end{{minipage}}"
            f"\\hfill\n\\begin{{minipage}}{{0.3\\textwidth}}\n"
            f"\\includegraphics[width=\\textwidth]{{{portrait}}}\n\\end{{minipage}}"
        )
    else:
        personal_section = personal_table

    return f"""\
\\documentclass[11pt]{{article}}
\\usepackage[margin=1in]{{geometry}}
\\usepackage{{parskip}}
\\usepackage{{array}}
{graphicx}\\begin{{document}}

\\begin{{center}}
\\textbf{{\\Large PERSON OF INTEREST -- INFORMATION FORM}}
\\end{{center}}

\\hrule\\bigskip

\\textbf{{\\large PERSONAL DETAILS}}\\\\[0.5em]
{personal_section}

\\bigskip
\\textbf{{\\large CONTACT INFORMATION}}\\\\[0.5em]
\\begin{{tabular}}{{|l|l|}}
\\hline
\\textbf{{Phone}} & {_latex_escape(item.phone_country_code)} {_latex_escape(item.phone_number)} \\\\\\hline
\\textbf{{Address}} & {_latex_escape(address)} \\\\\\hline
\\end{{tabular}}

\\bigskip
\\textbf{{\\large PHYSICAL DESCRIPTION}}\\\\[0.5em]
\\begin{{tabular}}{{|l|l|}}
\\hline
\\textbf{{Height (cm)}} & {_latex_escape(item.height_cm or "N/A")} \\\\\\hline
\\textbf{{Weight (kg)}} & {_latex_escape(item.weight_kg or "N/A")} \\\\\\hline
\\textbf{{Eye Color}} & {_latex_escape(item.eye_color or "N/A")} \\\\\\hline
\\textbf{{Hair Color}} & {_latex_escape(item.hair_color or "N/A")} \\\\\\hline
\\textbf{{Shoe Size (EU)}} & {_latex_escape(item.shoe_size_eu or "N/A")} \\\\\\hline
\\end{{tabular}}

\\bigskip
\\textbf{{\\large ADDITIONAL INFORMATION}}\\\\[0.5em]
\\begin{{tabular}}{{|l|l|}}
\\hline
\\textbf{{Vehicle Plates}} & {_latex_escape(item.vehicle_plates or "N/A")} \\\\\\hline
\\textbf{{Employer}} & {_latex_escape(item.employer or "N/A")} \\\\\\hline
\\textbf{{Prior Arrests}} & {"Yes" if item.prior_arrests else "No"} \\\\\\hline
\\textbf{{Prior Convictions}} & {"Yes" if item.prior_convictions else "No"} \\\\\\hline
\\end{{tabular}}

\\bigskip\\hrule\\medskip
\\textbf{{Signature:}} \\textit{{{_latex_escape(item.signature or "")}}} \\hfill \\textbf{{Date:}}

\\end{{document}}"""


def _poi_html(item: PersonOfInterestForm, portrait: str | None) -> str:
    full_name = _poi_full_name(item)
    address = _poi_address(item)

    photo_td = ""
    if portrait:
        photo_td = (
            f'<td rowspan="6" style="width: 150px; vertical-align: top; padding: 8px;">'
            f'<img src="{portrait}" style="width: 100%; border: 1px solid #ccc;"></td>'
        )

    return f"""\
<!DOCTYPE html>
<html lang="en">
<head><meta charset="UTF-8">
<title>POI Form</title>
<style>
  body {{ font-family: Arial, sans-serif; max-width: 800px; margin: 40px auto; padding: 0 20px; }}
  h1 {{ text-align: center; font-size: 1.3em; }}
  h2 {{ font-size: 1em; margin: 1em 0 0.3em; }}
  table {{ width: 100%; border-collapse: collapse; margin-bottom: 0.5em; }}
  th, td {{ border: 1px solid #999; padding: 6px 10px; text-align: left; }}
  th {{ background: #f5f5f5; width: 160px; }}
  hr {{ border: none; border-top: 1px solid #999; margin: 1em 0; }}
</style>
</head>
<body>
<h1>PERSON OF INTEREST &mdash; INFORMATION FORM</h1>
<hr>

<h2>PERSONAL DETAILS</h2>
<table>
  <tr><th>Full Name</th><td>{_html_escape(full_name)}</td>{photo_td}</tr>
  <tr><th>Nickname</th><td>{_html_escape(item.nickname or "N/A")}</td></tr>
  <tr><th>Date of Birth</th><td>{_html_escape(item.date_of_birth)}</td></tr>
  <tr><th>Nationality</th><td>{_html_escape(item.nationality or "N/A")}</td></tr>
  <tr><th>ID Number</th><td>{_html_escape(item.id_number or "N/A")}</td></tr>
  <tr><th>Occupation</th><td>{_html_escape(item.occupation or "N/A")}</td></tr>
</table>

<h2>CONTACT INFORMATION</h2>
<table>
  <tr><th>Phone</th><td>{_html_escape(item.phone_country_code)} {_html_escape(item.phone_number)}</td></tr>
  <tr><th>Address</th><td>{_html_escape(address)}</td></tr>
</table>

<h2>PHYSICAL DESCRIPTION</h2>
<table>
  <tr><th>Height (cm)</th><td>{_html_escape(item.height_cm or "N/A")}</td></tr>
  <tr><th>Weight (kg)</th><td>{_html_escape(item.weight_kg or "N/A")}</td></tr>
  <tr><th>Eye Color</th><td>{_html_escape(item.eye_color or "N/A")}</td></tr>
  <tr><th>Hair Color</th><td>{_html_escape(item.hair_color or "N/A")}</td></tr>
  <tr><th>Shoe Size (EU)</th><td>{_html_escape(item.shoe_size_eu or "N/A")}</td></tr>
</table>

<h2>ADDITIONAL INFORMATION</h2>
<table>
  <tr><th>Vehicle Plates</th><td>{_html_escape(item.vehicle_plates or "N/A")}</td></tr>
  <tr><th>Employer</th><td>{_html_escape(item.employer or "N/A")}</td></tr>
  <tr><th>Prior Arrests</th><td>{"Yes" if item.prior_arrests else "No"}</td></tr>
  <tr><th>Prior Convictions</th><td>{"Yes" if item.prior_convictions else "No"}</td></tr>
</table>

<div style="margin-top: 2em;">
  <hr>
  <p><strong>Signature:</strong> <em>{_html_escape(item.signature or "")}</em></p>
</div>
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
        label = item.owner_name if msg.direction == "outgoing" else msg.other_party
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
        label = _latex_escape(item.owner_name if msg.direction == "outgoing" else msg.other_party)
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
\\end{{tabular}}

\\bigskip\\hrule\\bigskip

{chat}

\\end{{document}}"""


def _sms_html(item: SmsLog) -> str:
    msgs: list[str] = []
    for msg in item.messages:
        bg = "#e1f0ff" if msg.direction == "outgoing" else "#f0f0f0"
        label = _html_escape(item.owner_name if msg.direction == "outgoing" else msg.other_party)
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
</div>
<hr>
{chat}
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
