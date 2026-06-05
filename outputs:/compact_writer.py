"""
compact_writer.py
WHO DAK Intelligence Platform — outputs/compact_writer.py
Minimal JSON output for agent consumption. Minimum tokens.
"""
from __future__ import annotations
import json, datetime
from pathlib import Path

# Compact key abbreviations
SCHEMA = {
    "m":  "metadata (c=country,d=domain,s=score,cat=category,t=timestamp)",
    "b1": "block1 fields (v=value,y=year,cf=confidence_code,src=source_label)",
    "b2": "block2 fields",
    "rf": "active risk flag names",
    "mq": "number of moh_questions generated",
    "mq_list": "moh_questions list (optional, only if include_questions=True)",
    "fe": "feasibility note (SV/HQ only)",
}

CONF_COMPACT = {
    "verified":"V","verified-academic":"VA","inferred":"I",
    "inferred-weak":"IW","unknown":"U","CONTRADICTED":"C",
    # from evidence codes
    "F":"F","INF":"INF","OH":"OH","C":"C","U":"U",
}

def write(
    country_iso3: str, dak_domain: str,
    category_code: str, reliability_score: float,
    b1_fields: dict, b2_fields: dict,
    active_risk_flags: list[str],
    moh_questions: list[str],
    feasibility_note: str = "",
    output_dir: Path = None,
    include_questions: bool = False,
) -> dict:
    ts = datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M")
    doc = {
        "m": {
            "c":   country_iso3,
            "d":   dak_domain,
            "s":   round(reliability_score, 3),
            "cat": category_code,
            "t":   ts,
        },
        "b1": _compact_block(b1_fields),
        "b2": _compact_block(b2_fields),
        "rf": active_risk_flags,
        "mq": len(moh_questions),
    }
    if include_questions:
        doc["mq_list"] = moh_questions
    if feasibility_note:
        doc["fe"] = feasibility_note[:200]

    if output_dir:
        output_dir.mkdir(parents=True, exist_ok=True)
        path = output_dir / "profile.compact.json"
        path.write_text(json.dumps(doc, ensure_ascii=False, separators=(",",":")))

    return doc

def _compact_block(fields: dict) -> dict:
    out = {}
    for key, fld in fields.items():
        if isinstance(fld, dict):
            entry = {}
            if fld.get("value") not in (None, ""):
                entry["v"] = fld["value"]
            if fld.get("year"):
                entry["y"] = fld["year"]
            cf = fld.get("confidence_code") or fld.get("confidence", "")
            if cf:
                entry["cf"] = CONF_COMPACT.get(cf, cf)
            src = fld.get("source_label") or fld.get("source_url", "")
            if src:
                entry["src"] = src[:40]
            if entry:
                out[key] = entry
        elif fld is not None:
            out[key] = fld
    return out

def token_estimate(doc: dict) -> int:
    return len(json.dumps(doc, separators=(",",":"), ensure_ascii=False)) // 4

if __name__ == "__main__":
    sample = write(
        country_iso3="CRI", dak_domain="ANC",
        category_code="CE", reliability_score=0.77,
        b1_fields={
            "anc4_coverage": {"value": 99, "year": 2024, "confidence_code": "V", "source_label": "UNICEF"},
            "mmr": {"value": 22, "year": 2020, "confidence_code": "C", "source_label": "WHO-GHO/UNICEF"},
        },
        b2_fields={
            "poc_system_name": {"value": "EDUS", "confidence_code": "V", "source_label": "IDB-2023"},
            "poc_hmis_integration": {"value": False, "confidence_code": "V", "source_label": "PAHO"},
        },
        active_risk_flags=["RISK_VENDOR_IS_GOVERNMENT","RISK_INTEROPERABILITY_GAP"],
        moh_questions=["Q1","Q2","Q3","Q4","Q5"],
    )
    out = json.dumps(sample, separators=(",",":"))
    print(out)
    print(f"\nEstimated tokens: ~{len(out)//4}")
    print("✓ compact_writer OK")
