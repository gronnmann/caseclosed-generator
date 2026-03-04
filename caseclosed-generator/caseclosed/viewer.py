"""Web viewer for CaseClosed cases.

Provides a Flask app that serves a browsable, editable view of generated cases.
Launch via: ``uv run python main.py view [case_id]``
"""

from __future__ import annotations

import json

from flask import Flask, Response, abort, jsonify, request, send_from_directory

from caseclosed.persistence import load_case, save_case, list_cases, images_dir


def create_app() -> Flask:
    app = Flask(__name__, static_folder=None)

    # ── HTML routes ──────────────────────────────────────────────

    @app.route("/")
    def index() -> str:
        cases = list_cases()
        rows = "".join(
            f'<tr onclick="location.href=\'/case/{c.id}\'" style="cursor:pointer">'
            f"<td>{c.id}</td><td>{c.title or '-'}</td>"
            f"<td>{c.premise[:80]}{'...' if len(c.premise)>80 else ''}</td>"
            f"<td>{c.generation_state.phase.value}</td>"
            f"<td>{c.language}</td></tr>"
            for c in cases
        )
        return f"""<!DOCTYPE html><html><head><meta charset="utf-8">
<title>CaseClosed Viewer</title>
<style>{_base_css()}</style></head><body>
<div class="container"><h1>CaseClosed — Cases</h1>
<table><thead><tr><th>ID</th><th>Title</th><th>Premise</th><th>Phase</th><th>Lang</th></tr></thead>
<tbody>{rows}</tbody></table></div></body></html>"""

    @app.route("/case/<case_id>")
    def case_page(case_id: str) -> str:
        try:
            load_case(case_id)
        except FileNotFoundError:
            abort(404)
        return _viewer_html(case_id)

    # ── Image serving ────────────────────────────────────────────

    @app.route("/case/<case_id>/images/<path:filename>")
    def serve_image(case_id: str, filename: str) -> Response:
        img_dir = images_dir(case_id).resolve()
        return send_from_directory(img_dir, filename)

    # ── JSON API ─────────────────────────────────────────────────

    @app.route("/api/case/<case_id>")
    def api_case(case_id: str) -> Response:
        try:
            case = load_case(case_id)
        except FileNotFoundError:
            abort(404)
        return Response(
            case.model_dump_json(indent=2),
            mimetype="application/json",
        )

    @app.route("/api/case/<case_id>/truth", methods=["PUT"])
    def api_update_truth(case_id: str) -> Response:
        case = load_case(case_id)
        if not case.truth:
            abort(400, "No truth to update")
        data = request.get_json(force=True)
        truth_dict = case.truth.model_dump()
        truth_dict.update(data)
        from caseclosed.models.case import CaseTruth
        case.truth = CaseTruth.model_validate(truth_dict)
        save_case(case)
        return jsonify({"ok": True})

    @app.route("/api/case/<case_id>/suspect/<name>", methods=["PUT"])
    def api_update_suspect(case_id: str, name: str) -> Response:
        case = load_case(case_id)
        suspect = next(
            (s for s in case.suspects if s.name == name), None
        )
        if not suspect:
            abort(404, f"Suspect not found: {name}")
        data = request.get_json(force=True)
        idx = case.suspects.index(suspect)
        suspect_dict = suspect.model_dump()
        suspect_dict.update(data)
        from caseclosed.models.suspect import Suspect
        case.suspects[idx] = Suspect.model_validate(suspect_dict)
        save_case(case)
        return jsonify({"ok": True})

    @app.route("/api/case/<case_id>/episode/<int:number>", methods=["PUT"])
    def api_update_episode(case_id: str, number: int) -> Response:
        case = load_case(case_id)
        episode = next(
            (e for e in case.episodes if e.number == number), None
        )
        if not episode:
            abort(404, f"Episode {number} not found")
        data = request.get_json(force=True)
        idx = case.episodes.index(episode)
        ep_dict = episode.model_dump()
        ep_dict.update(data)
        from caseclosed.models.episode import Episode
        case.episodes[idx] = Episode.model_validate(ep_dict)
        save_case(case)
        return jsonify({"ok": True})

    @app.route("/api/case/<case_id>/evidence/<plan_id>", methods=["PUT"])
    def api_update_evidence(case_id: str, plan_id: str) -> Response:
        case = load_case(case_id)
        item = next(
            (e for e in case.evidence if getattr(e, "plan_id", None) == plan_id),
            None,
        )
        if not item:
            abort(404, f"Evidence not found: {plan_id}")
        data = request.get_json(force=True)
        idx = case.evidence.index(item)
        item_dict = item.model_dump()
        item_dict.update(data)

        # Re-validate with correct concrete type
        from caseclosed.models.evidence import EvidenceItem
        from pydantic import TypeAdapter
        adapter = TypeAdapter(EvidenceItem)
        case.evidence[idx] = adapter.validate_python(item_dict)
        save_case(case)
        return jsonify({"ok": True})

    @app.route("/api/case/<case_id>/evidence-plan/<plan_id>", methods=["PUT"])
    def api_update_evidence_plan(case_id: str, plan_id: str) -> Response:
        case = load_case(case_id)
        item = next(
            (p for p in case.evidence_plan if p.id == plan_id), None
        )
        if not item:
            abort(404, f"Plan item not found: {plan_id}")
        data = request.get_json(force=True)
        idx = case.evidence_plan.index(item)
        plan_dict = item.model_dump()
        plan_dict.update(data)
        from caseclosed.models.evidence import EvidencePlanItem
        case.evidence_plan[idx] = EvidencePlanItem.model_validate(plan_dict)
        save_case(case)
        return jsonify({"ok": True})

    @app.route("/api/case/<case_id>/image/<path:filename>", methods=["POST"])
    def api_replace_image(case_id: str, filename: str) -> Response:
        """Replace an image file via multipart upload."""
        if "file" not in request.files:
            abort(400, "No file uploaded")
        file = request.files["file"]
        if not file.filename:
            abort(400, "Empty filename")
        img_dir = images_dir(case_id)
        dest = img_dir / filename
        if not dest.resolve().is_relative_to(img_dir.resolve()):
            abort(400, "Invalid filename")
        file.save(str(dest))
        return jsonify({"ok": True, "filename": filename})

    return app


# ── HTML template ────────────────────────────────────────────────


def _base_css() -> str:
    return """\
* { box-sizing: border-box; margin: 0; padding: 0; }
body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
       background: #0f0f0f; color: #e0e0e0; line-height: 1.6; }
.container { max-width: 1200px; margin: 0 auto; padding: 20px; }
h1 { margin-bottom: 20px; color: #fff; }
h2 { color: #ffd54f; margin: 24px 0 12px; border-bottom: 1px solid #333; padding-bottom: 4px; }
h3 { color: #90caf9; margin: 16px 0 8px; }
table { width: 100%; border-collapse: collapse; background: #1a1a1a; border-radius: 8px; overflow: hidden; }
th, td { padding: 10px 14px; text-align: left; border-bottom: 1px solid #2a2a2a; }
th { background: #222; color: #aaa; font-weight: 600; text-transform: uppercase; font-size: 0.8em; }
tr:hover { background: #252525; }
a { color: #64b5f6; text-decoration: none; }
a:hover { text-decoration: underline; }

/* Navigation */
nav { position: fixed; top: 0; left: 0; width: 220px; height: 100vh; background: #141414;
      border-right: 1px solid #2a2a2a; padding: 16px; overflow-y: auto; z-index: 100; }
nav h2 { font-size: 1em; color: #ffd54f; border: none; margin: 16px 0 8px; padding: 0; }
nav a { display: block; padding: 6px 10px; border-radius: 4px; color: #bbb; font-size: 0.9em; }
nav a:hover, nav a.active { background: #252525; color: #fff; text-decoration: none; }
nav .back { color: #888; font-size: 0.85em; margin-bottom: 12px; }

main { margin-left: 240px; padding: 24px; max-width: 960px; }

/* Sections */
.section { background: #1a1a1a; border-radius: 8px; padding: 20px; margin-bottom: 20px; }
.section-header { display: flex; justify-content: space-between; align-items: center; }

/* Cards */
.card { background: #222; border-radius: 6px; padding: 16px; margin-bottom: 12px; border: 1px solid #333; }
.card-title { font-weight: 600; color: #fff; margin-bottom: 8px; }

/* Fields */
.field { margin-bottom: 10px; }
.field-label { font-size: 0.8em; color: #888; text-transform: uppercase; margin-bottom: 2px; }
.field-value { color: #ddd; }

/* Editable fields */
.editable { cursor: pointer; border-bottom: 1px dashed #555; transition: border-color 0.2s; }
.editable:hover { border-color: #64b5f6; }
textarea.editing { width: 100%; min-height: 80px; background: #1a1a1a; color: #e0e0e0;
                   border: 1px solid #64b5f6; border-radius: 4px; padding: 8px;
                   font-family: inherit; font-size: inherit; resize: vertical; }
input.editing { width: 100%; background: #1a1a1a; color: #e0e0e0;
                border: 1px solid #64b5f6; border-radius: 4px; padding: 6px 8px;
                font-family: inherit; font-size: inherit; }

/* Buttons */
.btn { padding: 6px 14px; border: none; border-radius: 4px; cursor: pointer;
       font-size: 0.85em; font-weight: 500; transition: background 0.2s; }
.btn-save { background: #2e7d32; color: #fff; }
.btn-save:hover { background: #388e3c; }
.btn-cancel { background: #555; color: #ddd; margin-left: 6px; }
.btn-cancel:hover { background: #666; }
.btn-replace { background: #1565c0; color: #fff; }
.btn-replace:hover { background: #1976d2; }
.btn-small { padding: 4px 10px; font-size: 0.8em; }

/* Images */
.evidence-image { max-width: 100%; border-radius: 6px; margin: 8px 0; }
.portrait { width: 80px; height: 80px; border-radius: 50%; object-fit: cover; margin-right: 12px; }

/* Dialogue */
.dialogue .line { margin-bottom: 6px; }
.dialogue .speaker { font-weight: 600; color: #90caf9; }
.dialogue .text { color: #ddd; }

/* Timeline */
.timeline-event { display: flex; gap: 12px; margin-bottom: 8px; }
.timeline-time { color: #ffd54f; font-weight: 600; min-width: 80px; }

/* Tags */
.tag { display: inline-block; background: #333; color: #aaa; padding: 2px 8px;
       border-radius: 12px; font-size: 0.8em; margin: 2px 4px 2px 0; }
.tag-killer { background: #b71c1c; color: #fff; }
.tag-episode { background: #1a237e; color: #9fa8da; }

/* Toast */
.toast { position: fixed; bottom: 20px; right: 20px; background: #2e7d32; color: #fff;
         padding: 12px 20px; border-radius: 6px; font-size: 0.9em;
         opacity: 0; transition: opacity 0.3s; z-index: 1000; }
.toast.show { opacity: 1; }
.toast.error { background: #c62828; }

/* Collapsible */
.collapse-toggle { cursor: pointer; user-select: none; }
.collapse-toggle::before { content: "\\25BC "; font-size: 0.8em; color: #666;
                           display: inline-block; transition: transform 0.2s; }
.collapse-toggle.collapsed::before { transform: rotate(-90deg); }
.collapse-content { overflow: hidden; }
.collapse-content.collapsed { display: none; }

/* hidden file input */
.hidden-input { display: none; }
"""


def _viewer_html(case_id: str) -> str:
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>CaseClosed Viewer</title>
<style>{_base_css()}</style>
</head>
<body>
<nav id="sidebar">
  <div class="back"><a href="/">&larr; All Cases</a></div>
  <div id="nav-links"></div>
</nav>
<main id="app"><p>Loading...</p></main>
<div class="toast" id="toast"></div>
<script>
{_viewer_js(case_id)}
</script>
</body></html>"""


def _viewer_js(case_id: str) -> str:
    return (
        "const CASE_ID = " + json.dumps(case_id) + ";\n" + r"""
let CASE = null;

// ── Utilities ───────────────────────────────────────────────

function toast(msg, isError) {
  const el = document.getElementById('toast');
  el.textContent = msg;
  el.className = 'toast show' + (isError ? ' error' : '');
  setTimeout(() => el.className = 'toast', 2500);
}

function esc(s) {
  if (s == null) return '';
  const d = document.createElement('div');
  d.textContent = String(s);
  return d.innerHTML;
}

async function apiPut(url, data) {
  const r = await fetch(url, {
    method: 'PUT',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify(data),
  });
  if (!r.ok) { toast('Save failed: ' + r.status, true); return false; }
  toast('Saved');
  return true;
}

// ── Editable field helpers ──────────────────────────────────

function makeEditable(value, fieldPath, saveUrl, saveKey, multiline) {
  const id = 'edit-' + fieldPath.replace(/[^a-zA-Z0-9]/g, '-');
  const display = multiline ? `<pre style="white-space:pre-wrap;margin:0">${esc(value)}</pre>` : esc(value);
  return `<span class="editable" id="${id}" onclick="startEdit('${id}', ${JSON.stringify(saveUrl)}, ${JSON.stringify(saveKey)}, ${JSON.stringify(fieldPath)}, ${!!multiline})">${display || '<em style="color:#666">empty</em>'}</span>`;
}

function startEdit(id, saveUrl, saveKey, fieldPath, multiline) {
  const el = document.getElementById(id);
  if (el.querySelector('textarea, input')) return; // already editing
  const current = getNestedValue(CASE, fieldPath);
  const val = current == null ? '' : String(current);
  if (multiline) {
    el.innerHTML = `<textarea class="editing" rows="6">${esc(val)}</textarea>
      <div style="margin-top:4px"><button class="btn btn-save btn-small" onclick="saveEdit('${id}', '${saveUrl}', '${saveKey}', '${fieldPath}', true)">Save</button>
      <button class="btn btn-cancel btn-small" onclick="render()">Cancel</button></div>`;
  } else {
    el.innerHTML = `<input class="editing" value="${esc(val)}">
      <button class="btn btn-save btn-small" onclick="saveEdit('${id}', '${saveUrl}', '${saveKey}', '${fieldPath}', false)">Save</button>
      <button class="btn btn-cancel btn-small" onclick="render()">Cancel</button>`;
    el.querySelector('input').addEventListener('keydown', e => {
      if (e.key === 'Enter') saveEdit(id, saveUrl, saveKey, fieldPath, false);
      if (e.key === 'Escape') render();
    });
  }
  const input = el.querySelector('textarea, input');
  input.focus();
  if (!multiline) input.select();
}

async function saveEdit(id, saveUrl, saveKey, fieldPath, multiline) {
  const el = document.getElementById(id);
  const input = el.querySelector(multiline ? 'textarea' : 'input');
  const newVal = input.value;
  // Build patch object
  const keys = saveKey.split('.');
  let patch = {};
  let cur = patch;
  for (let i = 0; i < keys.length - 1; i++) {
    cur[keys[i]] = {};
    cur = cur[keys[i]];
  }
  cur[keys[keys.length - 1]] = newVal;
  const ok = await apiPut(saveUrl, patch);
  if (ok) {
    setNestedValue(CASE, fieldPath, newVal);
    render();
  }
}

function getNestedValue(obj, path) {
  return path.split('.').reduce((o, k) => (o && o[k] !== undefined) ? o[k] : null, obj);
}

function setNestedValue(obj, path, val) {
  const keys = path.split('.');
  let cur = obj;
  for (let i = 0; i < keys.length - 1; i++) {
    if (!cur[keys[i]]) cur[keys[i]] = {};
    cur = cur[keys[i]];
  }
  cur[keys[keys.length - 1]] = val;
}

// ── Image replace ───────────────────────────────────────────

function replaceImage(filename) {
  const inp = document.createElement('input');
  inp.type = 'file';
  inp.accept = 'image/*';
  inp.onchange = async () => {
    const file = inp.files[0];
    if (!file) return;
    const form = new FormData();
    form.append('file', file);
    const r = await fetch(`/api/case/${CASE_ID}/image/${filename}`, {method:'POST', body:form});
    if (r.ok) {
      toast('Image replaced');
      // Force reload images
      document.querySelectorAll(`img[data-filename="${filename}"]`).forEach(img => {
        img.src = img.src.split('?')[0] + '?t=' + Date.now();
      });
    } else {
      toast('Upload failed', true);
    }
  };
  inp.click();
}

// ── Rendering ───────────────────────────────────────────────

function render() {
  if (!CASE) return;
  renderNav();
  renderMain();
}

function renderNav() {
  let html = `<h2>${esc(CASE.title || 'Untitled')}</h2>`;
  html += `<a href="#truth">Truth</a>`;
  html += `<a href="#personnel">Personnel</a>`;
  if (CASE.suspects.length) {
    html += `<h2>Suspects</h2>`;
    CASE.suspects.forEach(s => {
      html += `<a href="#suspect-${esc(s.name)}">${esc(s.name)}${s.is_killer ? ' <span class="tag tag-killer">K</span>' : ''}</a>`;
    });
  }
  if (CASE.episodes.length) {
    html += `<h2>Episodes</h2>`;
    CASE.episodes.forEach(ep => {
      html += `<a href="#episode-${ep.number}">Ep ${ep.number}: ${esc(ep.title)}</a>`;
    });
  }
  if (CASE.evidence.length) {
    html += `<h2>Evidence</h2>`;
    CASE.evidence.forEach(e => {
      const plan = CASE.evidence_plan.find(p => p.id === e.plan_id);
      html += `<a href="#evidence-${esc(e.plan_id)}">${esc(plan ? plan.title : e.plan_id)}</a>`;
    });
  }
  document.getElementById('nav-links').innerHTML = html;
}

function renderMain() {
  let html = '';
  html += renderTruth();
  html += renderPersonnel();
  html += renderSuspects();
  html += renderEpisodes();
  html += renderEvidencePlan();
  html += renderEvidence();
  document.getElementById('app').innerHTML = html;
}

function renderTruth() {
  const t = CASE.truth;
  if (!t) return '<div class="section"><h2>Truth</h2><p>Not generated yet.</p></div>';
  const url = `/api/case/${CASE_ID}/truth`;
  let html = `<div class="section" id="truth"><h2>Truth</h2>`;
  html += `<div class="card">`;
  html += field('Victim', `${esc(t.victim.name)}, ${t.victim.age}, ${esc(t.victim.occupation)}`);
  html += field('Cause of Death', esc(t.victim.cause_of_death));
  html += field('Description', makeEditable(t.victim.description, 'truth.victim.description', url, 'victim.description', true));
  html += field('Killer', `<span class="tag tag-killer">${esc(t.killer_name)}</span>`);
  html += field('Method', makeEditable(t.method, 'truth.method', url, 'method', false));
  html += field('Weapon', makeEditable(t.weapon, 'truth.weapon', url, 'weapon', false));
  html += field('Motive', makeEditable(t.motive, 'truth.motive', url, 'motive', true));
  html += field('Crime Scene', makeEditable(t.crime_scene, 'truth.crime_scene', url, 'crime_scene', true));
  html += field('Key Evidence', makeEditable(t.key_evidence_summary, 'truth.key_evidence_summary', url, 'key_evidence_summary', true));

  // Victim portrait
  if (t.victim.portrait_filename) {
    html += `<div class="field"><div class="field-label">Victim Portrait</div>
      <img src="/case/${CASE_ID}/images/${t.victim.portrait_filename}" class="evidence-image" style="max-width:200px" data-filename="${esc(t.victim.portrait_filename)}">
      <br><button class="btn btn-replace btn-small" onclick="replaceImage('${esc(t.victim.portrait_filename)}')">Replace Image</button></div>`;
  }

  // Timeline
  if (t.timeline && t.timeline.length) {
    html += `<div class="field"><div class="field-label">Timeline</div>`;
    t.timeline.forEach(ev => {
      html += `<div class="timeline-event"><span class="timeline-time">${esc(ev.time)}</span>
        <span>${esc(ev.actor ? ev.actor + ': ' : '')}${esc(ev.description)}</span></div>`;
    });
    html += `</div>`;
  }

  // Suspect sketches
  if (t.suspect_sketches && t.suspect_sketches.length) {
    html += `<div class="field"><div class="field-label">Suspect Sketches</div>`;
    t.suspect_sketches.forEach(sk => {
      html += `<div class="card"><strong>${esc(sk.name)}</strong> (${esc(sk.role)})${sk.is_killer ? ' <span class="tag tag-killer">Killer</span>' : ''}
        <br>Motive: ${esc(sk.apparent_motive)}
        <br>Secret: ${esc(sk.secret)}
        <br>Connections: ${esc(sk.relationship_to_other_suspects)}</div>`;
    });
    html += `</div>`;
  }

  html += `</div></div>`;
  return html;
}

function renderPersonnel() {
  const p = CASE.personnel;
  if (!p) return '';
  let html = `<div class="section" id="personnel"><h2>Case Personnel</h2><div class="card">`;
  html += field('Lead Detective', esc(p.lead_detective));
  html += field('Interrogating Detective', esc(p.interrogating_detective));
  html += field('Coroner', esc(p.coroner));
  if (p.forensic_technician) html += field('Forensic Technician', esc(p.forensic_technician));
  html += `</div></div>`;
  return html;
}

function renderSuspects() {
  if (!CASE.suspects.length) return '';
  let html = `<div class="section"><h2>Suspects</h2>`;
  CASE.suspects.forEach((s, i) => {
    const url = `/api/case/${CASE_ID}/suspect/${encodeURIComponent(s.name)}`;
    html += `<div class="card" id="suspect-${esc(s.name)}">`;
    html += `<div class="card-title" style="display:flex;align-items:center">`;
    if (s.portrait_filename) {
      html += `<img src="/case/${CASE_ID}/images/${s.portrait_filename}" class="portrait" data-filename="${esc(s.portrait_filename)}">`;
    }
    html += `<div>${esc(s.name)}, ${s.age}, ${esc(s.occupation)}`;
    if (s.is_killer) html += ` <span class="tag tag-killer">Killer</span>`;
    html += `</div></div>`;

    // Portrait replace
    if (s.portrait_filename) {
      html += `<button class="btn btn-replace btn-small" style="margin-bottom:8px" onclick="replaceImage('${esc(s.portrait_filename)}')">Replace Portrait</button>`;
    }

    html += field('Relationship to Victim', makeEditable(s.relationship_to_victim, `suspects.${i}.relationship_to_victim`, url, 'relationship_to_victim', false));
    html += field('Motive', makeEditable(s.motive, `suspects.${i}.motive`, url, 'motive', true));
    html += field('Alibi', makeEditable(s.alibi, `suspects.${i}.alibi`, url, 'alibi', true));
    html += field('Alibi Truth', makeEditable(s.alibi_truth, `suspects.${i}.alibi_truth`, url, 'alibi_truth', true));
    if (s.secrets && s.secrets.length) {
      html += field('Secrets', s.secrets.map(x => `<span class="tag">${esc(x)}</span>`).join(' '));
    }
    if (s.personality_traits && s.personality_traits.length) {
      html += field('Personality', s.personality_traits.map(x => `<span class="tag">${esc(x)}</span>`).join(' '));
    }
    if (s.relationships && Object.keys(s.relationships).length) {
      html += field('Relationships', Object.entries(s.relationships).map(([k,v]) => `<strong>${esc(k)}:</strong> ${esc(v)}`).join('<br>'));
    }

    // Physical details (collapsible)
    html += `<div class="field"><span class="collapse-toggle collapsed" onclick="this.classList.toggle('collapsed');this.nextElementSibling.classList.toggle('collapsed')">Physical & Contact</span>
      <div class="collapse-content collapsed" style="margin-top:6px">`;
    if (s.height_cm) html += `Height: ${s.height_cm}cm &bull; `;
    if (s.weight_kg) html += `Weight: ${s.weight_kg}kg &bull; `;
    if (s.eye_color) html += `Eyes: ${esc(s.eye_color)} &bull; `;
    if (s.hair_color) html += `Hair: ${esc(s.hair_color)} &bull; `;
    if (s.phone_number) html += `<br>Phone: ${esc(s.phone_number)}`;
    if (s.address) html += `<br>Address: ${esc(s.address)}`;
    if (s.id_number) html += `<br>ID: ${esc(s.id_number)}`;
    if (s.vehicle_plates && s.vehicle_plates.length) html += `<br>Plates: ${s.vehicle_plates.map(x => esc(x)).join(', ')}`;
    html += `</div></div>`;

    html += `</div>`;
  });
  html += `</div>`;
  return html;
}

function renderEpisodes() {
  if (!CASE.episodes.length) return '';
  let html = `<div class="section"><h2>Episodes</h2>`;
  CASE.episodes.forEach(ep => {
    const url = `/api/case/${CASE_ID}/episode/${ep.number}`;
    html += `<div class="card" id="episode-${ep.number}">`;
    html += `<div class="card-title">Episode ${ep.number}: ${esc(ep.title)}</div>`;
    html += field('Objective', makeEditable(ep.objective, `episodes.${ep.number-1}.objective`, url, 'objective', false));
    html += field('Intro Letter', makeEditable(ep.intro_letter, `episodes.${ep.number-1}.intro_letter`, url, 'intro_letter', true));
    if (ep.previous_episode_solution) {
      html += field('Previous Episode Solution', makeEditable(ep.previous_episode_solution, `episodes.${ep.number-1}.previous_episode_solution`, url, 'previous_episode_solution', true));
    }
    if (ep.evidence_ids && ep.evidence_ids.length) {
      html += field('Evidence IDs', ep.evidence_ids.map(id => `<span class="tag tag-episode">${esc(id)}</span>`).join(' '));
    }
    if (ep.hints && ep.hints.length) {
      html += `<div class="field"><div class="field-label">Hints</div>`;
      ep.hints.forEach((h, hi) => {
        html += `<div>${hi+1}. ${makeEditable(h, `episodes.${ep.number-1}.hints.${hi}`, url, `hints`, true)}</div>`;
      });
      html += `</div>`;
    }
    html += `</div>`;
  });
  html += `</div>`;
  return html;
}

function renderEvidencePlan() {
  if (!CASE.evidence_plan.length) return '';
  let html = `<div class="section"><h2 class="collapse-toggle" onclick="this.classList.toggle('collapsed');this.nextElementSibling.classList.toggle('collapsed')">Evidence Plan (${CASE.evidence_plan.length} items)</h2>
    <div class="collapse-content">`;
  CASE.evidence_plan.forEach(p => {
    const url = `/api/case/${CASE_ID}/evidence-plan/${encodeURIComponent(p.id)}`;
    html += `<div class="card">`;
    html += `<div class="card-title">[${esc(p.type)}] ${esc(p.title)} <span class="tag tag-episode">Ep ${p.introduced_in_episode}</span></div>`;
    html += field('ID', esc(p.id));
    html += field('Description', makeEditable(p.brief_description, `evidence_plan_${p.id}.brief_description`, url, 'brief_description', true));
    html += field('Clue Reveals', makeEditable(p.clue_reveals, `evidence_plan_${p.id}.clue_reveals`, url, 'clue_reveals', true));
    if (p.suspect_name) html += field('Suspect', esc(p.suspect_name));
    if (p.also_used_in_episodes && p.also_used_in_episodes.length) {
      html += field('Also Used In', p.also_used_in_episodes.map(n => `<span class="tag tag-episode">Ep ${n}</span>`).join(' '));
    }
    html += `</div>`;
  });
  html += `</div></div>`;
  return html;
}

function renderEvidence() {
  if (!CASE.evidence.length) return '';
  // Group by episode
  const byEpisode = {};
  CASE.evidence.forEach(e => {
    const plan = CASE.evidence_plan.find(p => p.id === e.plan_id);
    const ep = plan ? plan.introduced_in_episode : 0;
    if (!byEpisode[ep]) byEpisode[ep] = [];
    byEpisode[ep].push({evidence: e, plan});
  });

  let html = `<div class="section"><h2>Evidence</h2>`;
  Object.keys(byEpisode).sort((a,b) => a-b).forEach(epNum => {
    html += `<h3>Episode ${epNum}</h3>`;
    byEpisode[epNum].forEach(({evidence: e, plan}) => {
      html += renderEvidenceItem(e, plan);
    });
  });
  html += `</div>`;
  return html;
}

function renderEvidenceItem(e, plan) {
  const url = `/api/case/${CASE_ID}/evidence/${encodeURIComponent(e.plan_id)}`;
  let html = `<div class="card" id="evidence-${esc(e.plan_id)}">`;
  html += `<div class="card-title">[${esc(e.type)}] ${esc(plan ? plan.title : e.plan_id)}</div>`;

  switch (e.type) {
    case 'interrogation':
      html += field('Suspect', esc(e.suspect_name));
      html += field('Case #', esc(e.case_number));
      html += field('Date', esc(e.date));
      html += field('Interviewer', esc(e.interviewer));
      html += `<div class="field"><div class="field-label">Transcript</div><div class="dialogue">`;
      if (e.transcript) {
        e.transcript.forEach(line => {
          html += `<div class="line"><span class="speaker">${esc(line.speaker)}:</span> <span class="text">${esc(line.text)}</span></div>`;
        });
      }
      html += `</div></div>`;
      break;

    case 'poi_form':
      html += field('Name', `${esc(e.name)} ${esc(e.middle_name)} ${esc(e.last_name)}`);
      html += field('DOB', esc(e.date_of_birth));
      html += field('Nationality', esc(e.nationality));
      html += field('Occupation', esc(e.occupation));
      html += field('Phone', esc((e.phone_country_code||'') + ' ' + (e.phone_number||'')));
      html += field('Address', esc(`${e.street_address || ''}, ${e.city || ''} ${e.postal_code || ''}`));
      html += field('Physical', `${e.height_cm || '?'}cm, ${e.weight_kg || '?'}kg, Eyes: ${esc(e.eye_color)}, Hair: ${esc(e.hair_color)}`);
      if (e.vehicle_plates) html += field('Vehicle', esc(e.vehicle_plates));
      if (e.employer) html += field('Employer', esc(e.employer));
      break;

    case 'letter':
      html += field('From', esc(e.sender));
      html += field('To', esc(e.recipient));
      html += field('Type', esc(e.letter_type));
      if (e.date) html += field('Date', esc(e.date));
      html += field('Body', makeEditable(e.body_text, `evidence_${e.plan_id}.body_text`, url, 'body_text', true));
      break;

    case 'image':
      html += field('Caption', makeEditable(e.caption, `evidence_${e.plan_id}.caption`, url, 'caption', false));
      html += field('Context', makeEditable(e.location_context, `evidence_${e.plan_id}.location_context`, url, 'location_context', false));
      html += field('Image Prompt', makeEditable(e.image_prompt, `evidence_${e.plan_id}.image_prompt`, url, 'image_prompt', true));
      if (e.image_filename) {
        html += `<img src="/case/${CASE_ID}/images/${e.image_filename}" class="evidence-image" data-filename="${esc(e.image_filename)}">`;
        html += `<br><button class="btn btn-replace btn-small" onclick="replaceImage('${esc(e.image_filename)}')">Replace Image</button>`;
      }
      break;

    case 'raw_text':
      html += field('Format', esc(e.format_hint));
      html += field('Content', makeEditable(e.content, `evidence_${e.plan_id}.content`, url, 'content', true));
      break;

    case 'phone_log':
      html += field('Owner', esc(e.owner_name));
      html += field('Phone', esc(e.phone_number));
      if (e.entries && e.entries.length) {
        html += `<div class="field"><div class="field-label">Entries</div><table>
          <thead><tr><th>Time</th><th>Dir</th><th>Other Party</th><th>Duration</th></tr></thead><tbody>`;
        e.entries.forEach(en => {
          html += `<tr><td>${esc(en.timestamp)}</td><td>${esc(en.direction)}</td><td>${esc(en.other_party)}</td><td>${esc(en.duration)}</td></tr>`;
        });
        html += `</tbody></table></div>`;
      }
      break;

    case 'sms_log':
      html += field('Owner', esc(e.owner_name));
      html += field('Phone', esc(e.phone_number));
      html += field('Conversation with', esc(e.other_party));
      if (e.messages && e.messages.length) {
        html += `<div class="field"><div class="field-label">Messages</div>`;
        e.messages.forEach(m => {
          const align = m.direction === 'outgoing' ? 'margin-left:auto' : 'margin-right:auto';
          const bg = m.direction === 'outgoing' ? '#1a3a5c' : '#2a2a2a';
          const label = m.direction === 'outgoing' ? e.owner_name : e.other_party;
          html += `<div style="width:75%;${align};background:${bg};padding:8px 12px;border-radius:8px;margin-bottom:6px"><span style="color:#888;font-size:0.8em">${esc(m.timestamp)} — ${esc(label)}</span><br>${esc(m.text)}</div>`;
        });
        html += `</div>`;
      }
      break;

    case 'email':
      html += field('From', esc(e.from_address));
      html += field('To', esc(e.to_address));
      if (e.cc) html += field('CC', esc(e.cc));
      html += field('Subject', esc(e.subject));
      html += field('Date', esc(e.date));
      html += field('Body', makeEditable(e.body_text, `evidence_${e.plan_id}.body_text`, url, 'body_text', true));
      break;

    case 'handwritten_note':
      html += field('Author', esc(e.author));
      html += field('Context', esc(e.context));
      html += field('Content', makeEditable(e.content, `evidence_${e.plan_id}.content`, url, 'content', true));
      break;

    case 'instagram_post':
      html += field('Username', esc(e.username));
      html += field('Date', esc(e.date));
      html += field('Likes', e.likes);
      html += field('Caption', makeEditable(e.caption, `evidence_${e.plan_id}.caption`, url, 'caption', true));
      if (e.image_filename) {
        html += `<img src="/case/${CASE_ID}/images/${e.image_filename}" class="evidence-image" data-filename="${esc(e.image_filename)}">`;
        html += `<br><button class="btn btn-replace btn-small" onclick="replaceImage('${esc(e.image_filename)}')">Replace Image</button>`;
      }
      break;

    case 'facebook_post':
      html += field('Author', esc(e.author_name));
      html += field('Date', esc(e.date));
      html += field('Likes', e.likes);
      html += field('Content', makeEditable(e.content, `evidence_${e.plan_id}.content`, url, 'content', true));
      if (e.comments && e.comments.length) {
        html += field('Comments', e.comments.map(c => esc(c)).join('<br>'));
      }
      break;

    case 'invoice':
      html += field('Invoice #', esc(e.invoice_number));
      html += field('Date', esc(e.date));
      html += field('Seller', esc(e.seller_name));
      html += field('Buyer', esc(e.buyer_name));
      if (e.items && e.items.length) {
        html += `<div class="field"><div class="field-label">Items</div><table>
          <thead><tr><th>Description</th><th>Qty</th><th>Unit Price</th><th>Total</th></tr></thead><tbody>`;
        e.items.forEach(it => {
          html += `<tr><td>${esc(it.description)}</td><td>${it.quantity}</td><td>${esc(it.unit_price)}</td><td>${esc(it.total)}</td></tr>`;
        });
        html += `</tbody></table></div>`;
      }
      html += field('Total', esc(e.total));
      break;

    case 'receipt':
      html += field('Store', esc(e.store_name));
      html += field('Date', esc(e.date));
      if (e.items && e.items.length) {
        html += `<div class="field"><div class="field-label">Items</div><table>
          <thead><tr><th>Description</th><th>Qty</th><th>Price</th></tr></thead><tbody>`;
        e.items.forEach(it => {
          html += `<tr><td>${esc(it.description)}</td><td>${it.quantity}</td><td>${esc(it.price)}</td></tr>`;
        });
        html += `</tbody></table></div>`;
      }
      html += field('Total', esc(e.total));
      if (e.payment_method) html += field('Payment', esc(e.payment_method));
      break;

    default:
      html += `<pre style="white-space:pre-wrap;color:#aaa">${esc(JSON.stringify(e, null, 2))}</pre>`;
  }

  html += `</div>`;
  return html;
}

function field(label, valueHtml) {
  return `<div class="field"><div class="field-label">${esc(label)}</div><div class="field-value">${valueHtml}</div></div>`;
}

// ── Init ────────────────────────────────────────────────────

async function init() {
  const r = await fetch(`/api/case/${CASE_ID}`);
  CASE = await r.json();
  render();
  // Scroll to hash if present
  if (location.hash) {
    setTimeout(() => {
      const el = document.querySelector(location.hash);
      if (el) el.scrollIntoView({behavior: 'smooth', block: 'start'});
    }, 100);
  }
}

init();
"""
    )
