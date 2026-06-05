"""
http_client.py
WHO DAK Intelligence Platform — retrieval/http_client.py

HTTP client with retry logic, error classification,
and retrieval state tracking. No business logic.
"""
from __future__ import annotations

import hashlib
import socket
import time
from dataclasses import dataclass
from typing import Optional
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from retrieval_states import (
    ACCESSIBLE, INACCESSIBLE, JS_BLOCKED, LANDING_PAGE_ONLY,
    NETWORK_FAILED, PARSED, REQUEST_FAILED,
)

USER_AGENT  = "who-dak-intelligence/1.0 (WHO DAK NLP Project)"
RETRY_WAIT  = 1.5   # seconds between retries
MAX_RETRIES = 1     # one retry on timeout only


@dataclass
class HTTPResult:
    url:           str
    state:         str
    status_code:   Optional[int]   = None
    content:       Optional[bytes] = None
    content_type:  str             = ""
    final_url:     str             = ""
    sha256:        str             = ""
    error_type:    str             = ""
    error_msg:     str             = ""
    retrieval_ms:  int             = 0


def fetch(url: str, timeout: int = 20) -> HTTPResult:
    """
    Fetch a URL. Retry once on timeout.
    Classifies errors into retrieval states.
    Never raises — always returns an HTTPResult.
    """
    for attempt in range(MAX_RETRIES + 1):
        result = _attempt(url, timeout)
        if result.state != NETWORK_FAILED or "timeout" not in result.error_type:
            return result
        if attempt < MAX_RETRIES:
            time.sleep(RETRY_WAIT)
    return result


def _attempt(url: str, timeout: int) -> HTTPResult:
    t0 = int(time.time() * 1000)
    req = Request(url, headers={
        "User-Agent":      USER_AGENT,
        "Accept":          "text/html,application/xhtml+xml,application/json,*/*",
        "Accept-Language": "en-US,en;q=0.9",
    })
    try:
        with urlopen(req, timeout=timeout) as resp:
            content      = resp.read()
            content_type = resp.headers.get("Content-Type", "")
            final_url    = resp.geturl()
            status_code  = resp.status
        sha   = hashlib.sha256(content).hexdigest()
        state = _classify(content, content_type, final_url)
        return HTTPResult(
            url=url, state=state, status_code=status_code,
            content=content, content_type=content_type,
            final_url=final_url, sha256=sha,
            retrieval_ms=int(time.time() * 1000) - t0,
        )
    except socket.timeout as e:
        return HTTPResult(url=url, state=NETWORK_FAILED,
            error_type="timeout", error_msg=str(e),
            retrieval_ms=int(time.time() * 1000) - t0)
    except socket.gaierror as e:
        return HTTPResult(url=url, state=NETWORK_FAILED,
            error_type="dns_error", error_msg=str(e),
            retrieval_ms=int(time.time() * 1000) - t0)
    except HTTPError as e:
        return HTTPResult(url=url, state=REQUEST_FAILED,
            status_code=e.code,
            error_type=f"http_{e.code}", error_msg=str(e),
            retrieval_ms=int(time.time() * 1000) - t0)
    except URLError as e:
        err_type = "timeout" if "timed out" in str(e).lower() else "url_error"
        return HTTPResult(url=url,
            state=NETWORK_FAILED if err_type == "timeout" else INACCESSIBLE,
            error_type=err_type, error_msg=str(e),
            retrieval_ms=int(time.time() * 1000) - t0)
    except Exception as e:
        return HTTPResult(url=url, state=INACCESSIBLE,
            error_type=type(e).__name__, error_msg=str(e),
            retrieval_ms=int(time.time() * 1000) - t0)


def _classify(content: bytes, content_type: str, url: str) -> str:
    """Classify what the response actually contains."""
    # PDF
    if (content.startswith(b"%PDF")
            or "pdf" in content_type.lower()
            or url.lower().endswith(".pdf")):
        return PARSED

    # JSON / structured data
    if "application/json" in content_type:
        return PARSED

    # HTML — check for JS wall or very short landing page
    if b"<html" in content[:500].lower():
        preview = content[:4000].lower()
        js_signals = [
            b"enable javascript", b"please enable",
            b"you need javascript", b"requires javascript",
            b"loading...", b"app-root", b"__next",
            b"window.__nuxt", b"react-root",
        ]
        if any(sig in preview for sig in js_signals):
            return JS_BLOCKED
        if len(content) < 3000:
            return LANDING_PAGE_ONLY
        return ACCESSIBLE

    return PARSED


def is_pdf(result: HTTPResult) -> bool:
    return (
        bool(result.content and result.content[:4] == b"%PDF")
        or "pdf" in result.content_type.lower()
        or result.url.lower().endswith(".pdf")
    )


if __name__ == "__main__":
    print("Testing http_client against live endpoints...")
    r1 = fetch("https://ghoapi.azureedge.net/api/WHS4_100?$top=1")
    assert r1.state == PARSED, f"GHO: {r1.state} {r1.error_msg}"
    print(f"✓ WHO GHO: {r1.state} {r1.retrieval_ms}ms")

    r2 = fetch("https://api.worldbank.org/v2/country/ZMB/indicator/SP.POP.TOTL?format=json&per_page=1")
    assert r2.state == PARSED, f"WB: {r2.state} {r2.error_msg}"
    print(f"✓ World Bank: {r2.state} {r2.retrieval_ms}ms")

    r3 = fetch("https://does-not-exist-99999.example.com")
    assert is_failed(r3.state), f"Bad URL should fail: {r3.state}"
    print(f"✓ Bad domain: {r3.state} (correct)")

    from retrieval_states import is_failed
    print("All http_client tests passed.")
