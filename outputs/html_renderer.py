"""
html_renderer.py
WHO DAK Intelligence Platform — outputs/html_renderer.py
Human-readable HTML profile. Every field has a clickable source chip.
"""
from __future__ import annotations
import datetime
from pathlib import Path

CONF_COLOR = {
    "V":"#16A34A","VA":"#0D9488","I":"#CA8A04",
    "IW":"#EA580C","U":"#64748B","C":"#DC2626",
}
CONF_LABEL = {
    "V":"verified","VA":"verified-academic","I":"inferred",
    "IW":"inferred-weak","U":"unknown","C":"CONTRADICTED",
}
SEV_COLOR = {"high":"#DC2626","medium":"#CA8A04","informational":"#0D9488"}

def render(
    country_name: str, dak_domain: str,
    category_code: str, category_label: str,
    reliability_score: float, reliability_label: str,
    b1_fields: dict, b2_fields: dict,
    active_flags: list[dict],
    moh_questions: list[str],
    b2_priming: dict = None,
    feasibility_note: str = "",
    output_dir: Path = None,
) -> str:
    ts = datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")
    score_color = ("#16A34A" if reliability_score >= 0.80 else
                   "#CA8A04" if reliability_score >= 0.60 else "#DC2626")
    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>WHO DAK Profile — {country_name} · {dak_domain}</title>
<style>
*{{box-sizing:border-box;margin:0;padding:0}}
body{{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;
  background:#F4F7FB;color:#1E293B;line-height:1.6;font-size:14px}}
.header{{background:#1E3A5F;color:#fff;padding:24px 32px}}
.header h1{{font-size:22px;font-weight:600;margin-bottom:4px}}
.header .meta{{font-size:12px;color:#CADCFC;margin-top:6px}}
.badge{{display:inline-block;padding:3px 10px;border-radius:12px;
  font-size:11px;font-weight:600;letter-spacing:.04em;margin-left:8px}}
.score-badge{{background:{score_color};color:#fff;font-size:13px;padding:5px 14px}}
.container{{max-width:1100px;margin:0 auto;padding:24px 20px}}
.section{{background:#fff;border:1px solid #E2E8F0;border-radius:10px;
  margin-bottom:18px;overflow:hidden}}
.section-header{{background:#F8FAFC;border-bottom:1px solid #E2E8F0;
  padding:12px 20px;font-size:13px;font-weight:600;color:#1E3A5F;
  cursor:pointer;user-select:none;display:flex;justify-content:space-between}}
.section-body{{padding:16px 20px}}
table{{width:100%;border-collapse:collapse;font-size:13px}}
th{{text-align:left;padding:7px 10px;background:#F8FAFC;color:#64748B;
  font-weight:500;font-size:11px;text-transform:uppercase;letter-spacing:.04em;
  border-bottom:1px solid #E2E8F0}}
td{{padding:7px 10px;border-bottom:1px solid #F1F5F9;vertical-align:top}}
tr:last-child td{{border-bottom:none}}
.chip{{display:inline-flex;align-items:center;gap:4px;padding:2px 8px;
  border-radius:12px;font-size:11px;font-weight:500;color:#fff;
  cursor:pointer;text-decoration:none;white-space:nowrap}}
.chip:hover{{opacity:.85}}
.field-val{{font-weight:500;color:#1E293B}}
.flag-card{{border-left:4px solid;padding:10px 14px;margin-bottom:10px;
  border-radius:0 6px 6px 0;background:#FFF}}
.flag-impact{{font-size:12px;color:#64748B;margin-top:4px}}
.flag-q{{font-size:12px;color:#1E3A5F;margin-top:6px;font-style:italic}}
.q-list{{counter-reset:q}}
.q-item{{counter-increment:q;padding:8px 12px;margin-bottom:6px;
  background:#F8FAFC;border-radius:6px;border-left:3px solid #0D9488;
  font-size:13px}}
.q-item::before{{content:counter(q)". ";font-weight:600;color:#0D9488}}
.feasibility{{background:#1E3A5F;color:#CADCFC;padding:14px 18px;
  border-radius:8px;font-size:13px;margin-bottom:16px}}
.priming-box{{background:#F0FDF4;border:1px solid #BBF7D0;border-radius:6px;
  padding:10px 14px;font-size:12px;color:#166534;margin-top:8px}}
footer{{text-align:center;color:#94A3B8;font-size:11px;padding:20px;margin-top:8px}}
</style>
</head>
<body>
<div class="header">
  <h1>{country_name} — {dak_domain} DAK Country Profile
    <span class="badge score-badge">{reliability_score:.2f} {reliability_label}</span>
  </h1>
  <div class="meta">
    Category: [{category_code}] {category_label} &nbsp;·&nbsp;
    Generated: {ts} &nbsp;·&nbsp;
    WHO DAK Intelligence Platform v2.0
  </div>
</div>
<div class="container">
"""
    # Feasibility note
    if feasibility_note:
        html += f'<div class="feasibility"><strong>⚠ Localization pathway:</strong> {feasibility_note}</div>\n'

    # B2 priming (collapsible)
    if b2_priming and any(b2_priming.values()):
        html += _section("Block 1 → Block 2 Priming Signals",
                         _priming_html(b2_priming))

    # Block 1
    html += _section("Block 1 — Health System Context",
                     _fields_table(b1_fields))

    # Block 2
    html += _section("Block 2 — Digital Landscape",
                     _fields_table(b2_fields))

    # Risk flags
    flag_html = _flags_html(active_flags)
    html += _section(f"Risk Flags ({len(active_flags)} active)", flag_html)

    # MoH questions
    html += _section("Questions for MoH Meeting", _questions_html(moh_questions))

    html += "<footer>WHO DAK Intelligence Platform — source attribution required for all claims</footer>\n"
    html += "</div>\n</body>\n</html>"

    if output_dir:
        output_dir.mkdir(parents=True, exist_ok=True)
        (output_dir / "profile.html").write_text(html, encoding="utf-8")

    return html


def _chip(label: str, url: str, conf_code: str,
          pub_date: str = "", retrieved: str = "") -> str:
    color  = CONF_COLOR.get(conf_code, "#64748B")
    title  = (f"{CONF_LABEL.get(conf_code,conf_code)} · "
              f"{label}"
              + (f" · pub:{pub_date}" if pub_date else "")
              + (f" · retrieved:{retrieved}" if retrieved else ""))
    if url and url.startswith("http"):
        return (f'<a class="chip" style="background:{color}" '
                f'href="{url}" target="_blank" title="{title}">'
                f'{label} <span>↗</span></a>')
    return (f'<span class="chip" style="background:{color}" '
            f'title="{title}">{label}</span>')


def _fields_table(fields: dict) -> str:
    if not fields:
        return "<p style='color:#94A3B8;font-size:13px'>No fields retrieved.</p>"
    rows = ""
    for key, fld in fields.items():
        if not isinstance(fld, dict):
            continue
        val  = fld.get("value")
        cf   = fld.get("confidence_code","U")
        src  = fld.get("source_label","")
        url  = fld.get("source_url","")
        pub  = str(fld.get("year","") or fld.get("pub_date",""))
        ret  = fld.get("retrieval_date","")
        note = fld.get("note","")
        disp = ("—" if val is None else
                ("⚠ CONTRADICTED" if cf == "C" else str(val)))
        chip = _chip(src or url[:30], url, cf, pub, ret)
        rows += (f"<tr><td style='color:#64748B;font-size:12px'>{key}</td>"
                 f"<td class='field-val'>{disp}</td>"
                 f"<td>{chip}</td>"
                 f"<td style='font-size:11px;color:#94A3B8'>{note[:80]}</td></tr>")
    return (f"<table><tr>"
            f"<th style='width:22%'>Field</th><th style='width:28%'>Value</th>"
            f"<th style='width:22%'>Source</th><th>Note</th></tr>"
            f"{rows}</table>")


def _flags_html(flags: list[dict]) -> str:
    if not flags:
        return "<p style='color:#16A34A;font-size:13px'>✓ No risk flags activated.</p>"
    html = ""
    for f in flags:
        sev   = f.get("severity","medium")
        color = SEV_COLOR.get(sev,"#CA8A04")
        html += (f'<div class="flag-card" style="border-color:{color}">'
                 f'<strong style="color:{color}">{f.get("name","")} '
                 f'<span class="badge" style="background:{color};color:#fff">{sev}</span></strong>'
                 f'<div class="flag-impact">{f.get("dak_impact","")[:200]}</div>'
                 f'<div class="flag-q">❓ {f.get("mandatory_moh_question","")[:250]}</div>'
                 f'</div>')
    return html


def _questions_html(questions: list[str]) -> str:
    items = "".join(f'<div class="q-item">{q}</div>' for q in questions)
    return f'<div class="q-list">{items}</div>'


def _priming_html(priming: dict) -> str:
    parts = []
    if priming.get("expected_systems"):
        sys_list = ", ".join(
            f'{s} ({int(c*100)}%)'
            for s,c in priming.get("expected_system_confidence",{}).items()
        ) or ", ".join(priming["expected_systems"])
        parts.append(f"<strong>Expected systems:</strong> {sys_list}")
    if priming.get("dak_use_case") and priming["dak_use_case"] != "standard":
        parts.append(f"<strong>DAK use case:</strong> {priming['dak_use_case']}")
    if priming.get("risk_flags_to_anticipate"):
        parts.append(f"<strong>Flags to anticipate:</strong> "
                     f"{', '.join(priming['risk_flags_to_anticipate'])}")
    notes = priming.get("source_strategy_notes",[])[:2]
    for n in notes:
        parts.append(f"<em>{n}</em>")
    return f'<div class="priming-box">{"<br>".join(parts)}</div>' if parts else ""


def _section(title: str, body: str) -> str:
    return (f'<div class="section">'
            f'<div class="section-header">{title}<span>▾</span></div>'
            f'<div class="section-body">{body}</div>'
            f'</div>\n')


if __name__ == "__main__":
    import tempfile, os
    with tempfile.TemporaryDirectory() as d:
        html = render(
            country_name="Costa Rica", dak_domain="ANC",
            category_code="CE", category_label="Centralized National Health System",
            reliability_score=0.77, reliability_label="MEDIUM CONFIDENCE",
            b1_fields={
                "anc4_coverage": {"value":"99%","year":2024,"confidence_code":"V",
                    "source_label":"UNICEF","source_url":"https://data.unicef.org/country/cr/"},
                "mmr": {"value":"22 vs 24","confidence_code":"C",
                    "source_label":"WHO-GHO/UNICEF","source_url":"https://ghoapi.azureedge.net",
                    "note":"CONTRADICTED: 2020 vs 2023 estimates"},
            },
            b2_fields={
                "poc_system_name": {"value":"EDUS","confidence_code":"V",
                    "source_label":"IDB 2023","source_url":"https://publications.iadb.org"},
                "poc_hmis_integration": {"value":False,"confidence_code":"V",
                    "source_label":"PAHO","source_url":"https://paho.org"},
            },
            active_flags=[{
                "name":"RISK_VENDOR_IS_GOVERNMENT","severity":"medium",
                "dak_impact":"Step 4 requires institutional IT commitment.",
                "mandatory_moh_question":"Does CCSS IT have 2026-27 DAK capacity?",
            }],
            moh_questions=["What is the CCSS roadmap for EDUS integration?",
                           "Is there an EDUS-SIVEI data flow for ANC indicators?",
                           "Has CCSS reviewed WHO ANC DAK content standards?",
                           "What quality monitoring metrics track beyond coverage?",
                           "Which health areas have the largest ANC quality gap?"],
            output_dir=Path(d),
        )
        size = len(html)
        assert (Path(d)/"profile.html").exists()
        print(f"✓ html_renderer: {size:,} bytes — profile.html written")
