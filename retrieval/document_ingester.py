"""
document_ingester.py
WHO DAK Intelligence Platform — retrieval/document_ingester.py

Handles documents provided by the WHO agent:
  user_pdf      — bytes or Path to a PDF
  user_url      — URL passed explicitly by the agent
  json_payload  — dict from an external RAG or WHO tool
  who_rag       — WHO RAG query result (dict with text key)
  who_mcp       — WHO smart-mcp-server stub (not yet available)

Agent-provided documents are processed BEFORE any web fetch.
"""
from __future__ import annotations
import hashlib, json, re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional
from retrieval_states import PARSED, INACCESSIBLE, REQUEST_FAILED, MACHINE_UNREADABLE

MAX_TEXT = 5000


@dataclass
class IngestedDocument:
    title:        str
    source_type:  str
    origin:       str
    state:        str
    text_extract: str  = ""
    source_url:   str  = ""
    local_path:   str  = ""
    sha256:       str  = ""
    parse_error:  str  = ""
    install_prompt: str = ""
    metadata:     dict = field(default_factory=dict)


@dataclass
class IngestionResult:
    documents: list[IngestedDocument] = field(default_factory=list)
    errors:    list[str]              = field(default_factory=list)

    @property
    def usable(self):
        return [d for d in self.documents if d.state == PARSED and d.text_extract]

    @property
    def failed(self):
        return [d for d in self.documents if d.state != PARSED]


def ingest(
    source_type: str,
    payload:     object,
    title:       str = "",
    output_dir:  Optional[Path] = None,
) -> IngestedDocument:
    if source_type == "user_pdf":
        return _pdf(payload, title, output_dir)
    if source_type == "user_url":
        return _url(str(payload), title)
    if source_type in ("json_payload", "who_rag"):
        return _json(payload, title, origin=source_type)
    if source_type == "who_mcp":
        return _mcp_stub(payload, title)
    return IngestedDocument(title=title, source_type=source_type, origin=source_type,
        state=MACHINE_UNREADABLE, parse_error=f"Unknown source_type: '{source_type}'")


def ingest_many(sources: list[dict], output_dir: Optional[Path] = None) -> IngestionResult:
    result = IngestionResult()
    for s in sources:
        try:
            result.documents.append(ingest(
                s["source_type"], s["payload"],
                title=s.get("title",""), output_dir=output_dir,
            ))
        except Exception as e:
            result.errors.append(f"{s.get('title','?')}: {e}")
    return result


# ── PDF ───────────────────────────────────────────────────────

def _pdf(payload, title, output_dir):
    try:
        if isinstance(payload, (str, Path)):
            p = Path(payload)
            if not p.exists():
                return IngestedDocument(title=title, source_type="pdf", origin="user_pdf",
                    state=INACCESSIBLE, local_path=str(payload),
                    parse_error=f"File not found: {payload}")
            content = p.read_bytes()
        elif isinstance(payload, (bytes, bytearray)):
            content = bytes(payload)
        else:
            return IngestedDocument(title=title, source_type="pdf", origin="user_pdf",
                state=MACHINE_UNREADABLE, parse_error=f"Unsupported type: {type(payload).__name__}")
    except Exception as e:
        return IngestedDocument(title=title, source_type="pdf", origin="user_pdf",
            state=REQUEST_FAILED, parse_error=str(e))

    sha = hashlib.sha256(content).hexdigest()
    saved = ""
    if output_dir:
        output_dir.mkdir(parents=True, exist_ok=True)
        slug = re.sub(r"[^a-zA-Z0-9]+", "-", title).strip("-").lower()[:50] or "doc"
        dest = output_dir / f"{slug}_{sha[:8]}.pdf"
        if not dest.exists():
            dest.write_bytes(content)
        saved = str(dest)

    text, err, prompt = _parse_pdf(content)
    return IngestedDocument(title=title or "Uploaded PDF", source_type="pdf",
        origin="user_pdf", state=PARSED if text else REQUEST_FAILED,
        text_extract=text, local_path=saved, sha256=sha,
        parse_error=err, install_prompt=prompt)


def _parse_pdf(content: bytes) -> tuple[str, str, str]:
    try:
        from io import BytesIO
        from pypdf import PdfReader
        r = PdfReader(BytesIO(content))
        parts, total = [], 0
        for page in r.pages[:10]:
            chunk = (page.extract_text() or "").strip()
            parts.append(chunk); total += len(chunk)
            if total >= MAX_TEXT: break
        return " ".join(parts)[:MAX_TEXT], "", ""
    except ImportError:
        return "", "pypdf not installed", "pip install pypdf>=6.0"
    except Exception as e:
        return "", str(e), ""


# ── URL ───────────────────────────────────────────────────────

def _url(url: str, title: str) -> IngestedDocument:
    try:
        from http_client import fetch, is_pdf
        result = fetch(url, timeout=20)
        if result.content and is_pdf(result):
            text, err, _ = _parse_pdf(result.content)
            return IngestedDocument(title=title or url[:60], source_type="pdf",
                origin="user_url", state=PARSED if text else REQUEST_FAILED,
                text_extract=text, source_url=url,
                sha256=result.sha256, parse_error=err)
        if result.content:
            text = _strip_html(result.content)
            return IngestedDocument(title=title or url[:60], source_type="html",
                origin="user_url", state=PARSED if text else MACHINE_UNREADABLE,
                text_extract=text[:MAX_TEXT], source_url=result.final_url or url,
                sha256=result.sha256)
        return IngestedDocument(title=title or url[:60], source_type="url",
            origin="user_url", state=result.state,
            source_url=url, parse_error=result.error_msg)
    except Exception as e:
        return IngestedDocument(title=title or url[:60], source_type="url",
            origin="user_url", state=INACCESSIBLE,
            source_url=url, parse_error=str(e))


def _strip_html(content: bytes) -> str:
    import html as h
    text = content.decode("utf-8", "replace")
    text = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", text, flags=re.S|re.I)
    text = re.sub(r"<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", h.unescape(text)).strip()


# ── JSON / RAG ────────────────────────────────────────────────

def _json(payload, title, origin) -> IngestedDocument:
    if isinstance(payload, str):
        try:
            payload = json.loads(payload)
        except json.JSONDecodeError:
            return IngestedDocument(title=title or "Text", source_type="text",
                origin=origin, state=PARSED, text_extract=payload[:MAX_TEXT])

    if not isinstance(payload, dict):
        return IngestedDocument(title=title, source_type="json", origin=origin,
            state=MACHINE_UNREADABLE,
            parse_error=f"Expected dict, got {type(payload).__name__}")

    text = ""
    for key in ("text","content","summary","excerpt","body","passage"):
        if payload.get(key):
            text = str(payload[key])[:MAX_TEXT]; break

    meta = {k:v for k,v in payload.items()
            if k not in ("text","content","summary","excerpt","body","passage")}
    return IngestedDocument(
        title=title or payload.get("title","RAG result"),
        source_type="json", origin=origin,
        state=PARSED if text else MACHINE_UNREADABLE,
        text_extract=text,
        source_url=payload.get("url","") or payload.get("source",""),
        metadata=meta,
        parse_error="" if text else "No text field found")


# ── WHO MCP stub ──────────────────────────────────────────────

def _mcp_stub(payload, title) -> IngestedDocument:
    """
    Replace body with real MCP call when smart-mcp-server is available:
        result = call_mcp_tool("fhir_apply_plandefinition", payload)
        return _json(result, title=title, origin="who_mcp")
    """
    return IngestedDocument(title=title or "WHO MCP", source_type="mcp",
        origin="who_mcp", state=INACCESSIBLE,
        parse_error=(
            "WHO MCP server not yet available. "
            "Activate in _mcp_stub() when smart-mcp-server is ready. "
            "See: DigitalSQR/smart-mcp-server"
        ))
