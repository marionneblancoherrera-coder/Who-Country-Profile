"""
manifest_loader.py
WHO DAK Intelligence Platform — retrieval/manifest_loader.py
Loads agent-discovered source URLs from a JSON manifest.
Country-specific URLs are never hardcoded — the agent discovers
and passes them here.
"""
from __future__ import annotations
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


@dataclass
class ManifestSource:
    title:             str
    publisher:         str
    source_type:       str
    url:               Optional[str] = None
    local_path:        Optional[str] = None
    source_class:      str = ""
    date:              str = ""
    evidence_role:     str = ""
    retrieval_priority: str = "medium"
    download_pdfs:     bool = False
    max_downloads:     int  = 2
    excerpt_keywords:  list = field(default_factory=list)
    country:           str = ""
    iso2:              str = ""
    dak_domain:        str = ""


@dataclass
class ManifestResult:
    sources:       list[ManifestSource]
    manifest_path: str
    total:         int
    matched:       int
    skipped:       int
    errors:        list[str]


def load(path: str | Path, country="", iso2="", dak_domain="") -> ManifestResult:
    path = Path(path)
    if not path.exists():
        return ManifestResult([], str(path), 0, 0, 0,
                              [f"Manifest not found: {path}"])
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        return ManifestResult([], str(path), 0, 0, 0, [f"JSON error: {e}"])

    raw = payload.get("sources", payload) if isinstance(payload, dict) else payload
    if not isinstance(raw, list):
        return ManifestResult([], str(path), 0, 0, 0,
                              ["Manifest must be a JSON array or {sources:[...]}"])

    sources, skipped, errors = [], 0, []
    for i, s in enumerate(raw, 1):
        if not isinstance(s, dict):
            errors.append(f"Entry {i}: not a dict"); skipped += 1; continue
        # Context filter — skip non-matching entries
        if country and s.get("country") and s["country"].lower() != country.lower():
            skipped += 1; continue
        if iso2 and s.get("iso2") and s["iso2"].upper() != iso2.upper():
            skipped += 1; continue
        if dak_domain and s.get("dak_domain") and s["dak_domain"].lower() != dak_domain.lower():
            skipped += 1; continue
        # Validate
        err = _validate(s, i)
        if err:
            errors.append(err); skipped += 1; continue
        sources.append(ManifestSource(
            title=s["title"], publisher=s["publisher"],
            source_type=s["source_type"],
            url=s.get("url"), local_path=s.get("local_path") or s.get("path"),
            source_class=s.get("source_class", s.get("source_type","")),
            date=s.get("date",""), evidence_role=s.get("evidence_role",""),
            retrieval_priority=s.get("retrieval_priority","medium"),
            download_pdfs=bool(s.get("download_pdfs",False)),
            max_downloads=int(s.get("max_downloads",2)),
            excerpt_keywords=s.get("excerpt_keywords",[]),
            country=s.get("country",""), iso2=s.get("iso2",""),
            dak_domain=s.get("dak_domain",""),
        ))

    return ManifestResult(sources, str(path), len(raw), len(sources), skipped, errors)


def empty() -> ManifestResult:
    return ManifestResult([], "(none)", 0, 0, 0, [])


def _validate(s: dict, i: int) -> str:
    for req in ("title","publisher","source_type"):
        if not s.get(req): return f"Entry {i}: missing '{req}'"
    has_url  = bool(s.get("url"))
    has_path = bool(s.get("local_path") or s.get("path"))
    if not has_url and not has_path:
        return f"Entry {i}: must have 'url' or 'local_path'"
    return ""
