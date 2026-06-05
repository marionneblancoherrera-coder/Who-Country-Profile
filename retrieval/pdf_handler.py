"""
pdf_handler.py
WHO DAK Intelligence Platform — retrieval/pdf_handler.py

PDF download, deduplication (SHA-256), and text extraction.
pypdf is optional — degrades gracefully without it.
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path

from retrieval_states import PARSED, REQUEST_FAILED

MAX_PARSE_CHARS = 5000
MAX_PAGES       = 8


@dataclass
class PDFResult:
    title:          str
    local_path:     str
    sha256:         str
    state:          str
    text_extract:   str  = ""
    parse_error:    str  = ""
    page_count:     int  = 0
    install_prompt: str  = ""


def process(
    content:    bytes,
    title:      str,
    output_dir: Path,
    source_url: str = "",
) -> PDFResult:
    """
    Save PDF (with SHA-256 dedup), extract text.
    Returns PDFResult with state=PARSED if text extracted.
    """
    sha256   = hashlib.sha256(content).hexdigest()
    out_path = _save_once(content, sha256, title, output_dir)
    text, error, pages, prompt = _extract(out_path)

    return PDFResult(
        title=title,
        local_path=str(out_path),
        sha256=sha256,
        state=PARSED if text else REQUEST_FAILED,
        text_extract=text[:MAX_PARSE_CHARS],
        parse_error=error,
        page_count=pages,
        install_prompt=prompt,
    )


def _save_once(content: bytes, sha256: str, title: str, output_dir: Path) -> Path:
    """Save PDF, reusing existing file if content is identical."""
    output_dir.mkdir(parents=True, exist_ok=True)

    # Dedup: check if same content already saved
    for existing in output_dir.glob("*.pdf"):
        if _sha256_file(existing) == sha256:
            return existing

    slug = re.sub(r"[^a-zA-Z0-9]+", "-", title).strip("-").lower()[:50] or "document"
    path = output_dir / f"{slug}.pdf"
    if path.exists() and _sha256_file(path) != sha256:
        path = output_dir / f"{slug}_{sha256[:8]}.pdf"

    if not path.exists():
        path.write_bytes(content)
    return path


def _extract(path: Path) -> tuple[str, str, int, str]:
    """Extract text from PDF. Returns (text, error, page_count, install_prompt)."""
    try:
        from pypdf import PdfReader
        reader = PdfReader(str(path))
        pages  = len(reader.pages)
        parts  = []
        total  = 0
        for page in reader.pages[:MAX_PAGES]:
            chunk = (page.extract_text() or "").strip()
            parts.append(chunk)
            total += len(chunk)
            if total >= MAX_PARSE_CHARS:
                break
        return " ".join(parts)[:MAX_PARSE_CHARS], "", pages, ""
    except ImportError:
        prompt = (
            "pypdf not installed. PDFs cannot be parsed.\n"
            "To enable: pip install pypdf>=6.0\n"
            "Without pypdf, PDFs are saved but text is not extracted."
        )
        return "", "pypdf not installed", 0, prompt
    except Exception as e:
        return "", str(e), 0, ""


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


if __name__ == "__main__":
    import tempfile
    with tempfile.TemporaryDirectory() as d:
        fake = b"%PDF-1.4 fake content"
        r1 = process(fake, "Test Document", Path(d))
        assert r1.sha256 != ""
        assert Path(r1.local_path).exists()

        # Dedup: same content → same file
        r2 = process(fake, "Test Document Copy", Path(d))
        assert r2.local_path == r1.local_path
        assert len(list(Path(d).glob("*.pdf"))) == 1

        print(f"✓ pdf_handler: save OK, SHA-256 dedup OK")
        print(f"  state={r1.state}, sha256={r1.sha256[:12]}...")
        if r1.install_prompt:
            print(f"  Note: {r1.install_prompt.splitlines()[0]}")
