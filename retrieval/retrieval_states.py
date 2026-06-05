"""
retrieval_states.py
WHO DAK Intelligence Platform — retrieval/retrieval_states.py

State machine constants for source retrieval lifecycle.
All retrieval components import states from here — no magic strings.
"""
from __future__ import annotations

# ── Retrieval states ──────────────────────────────────────────
DISCOVERED         = "discovered"       # source identified, not yet accessed
ACCESSIBLE         = "accessible"       # source reachable and responding
PARSED             = "parsed"           # content extracted and usable
PARTIALLY_PARSED   = "partially_parsed" # partial extraction succeeded
VALIDATED          = "validated"        # content reviewed and usable
LANDING_PAGE_ONLY  = "landing_page_only"# index page reached, doc not fetched
JS_BLOCKED         = "js_blocked"       # JavaScript wall — cannot fetch
PAYWALLED          = "paywalled"        # requires subscription
MACHINE_UNREADABLE = "machine_unreadable"
TRANSLATION_REQ    = "translation_required"
NETWORK_FAILED     = "network_failed"   # DNS error or timeout
REQUEST_FAILED     = "request_failed"   # HTTP 4xx / 5xx
INACCESSIBLE       = "inaccessible"     # unreachable by any method
SUPERSEDED         = "superseded"       # replaced by newer material

# Compact codes (match source_hierarchy.yml)
COMPACT = {
    DISCOVERED:          "DS",
    ACCESSIBLE:          "AC",
    PARSED:              "PA",
    PARTIALLY_PARSED:    "PP",
    VALIDATED:           "VA",
    LANDING_PAGE_ONLY:   "LP",
    JS_BLOCKED:          "JS",
    PAYWALLED:           "PW",
    MACHINE_UNREADABLE:  "MR",
    TRANSLATION_REQ:     "TR",
    NETWORK_FAILED:      "NF",
    REQUEST_FAILED:      "RF",
    INACCESSIBLE:        "IA",
    SUPERSEDED:          "SU",
}

# States where content can be cited
CITEABLE = {PARSED, VALIDATED, PARTIALLY_PARSED, ACCESSIBLE}

# States that indicate retrieval failure (NOT evidence of absence)
FAILED = {NETWORK_FAILED, REQUEST_FAILED, INACCESSIBLE, JS_BLOCKED}


def compact(state: str) -> str:
    """Return 2-letter compact code for a state."""
    return COMPACT.get(state, state[:2].upper())

def is_citeable(state: str) -> bool:
    return state in CITEABLE

def is_failed(state: str) -> bool:
    return state in FAILED


if __name__ == "__main__":
    assert is_citeable(PARSED)
    assert not is_citeable(JS_BLOCKED)
    assert is_failed(NETWORK_FAILED)
    assert compact(JS_BLOCKED) == "JS"
    assert compact(PARSED) == "PA"
    print(f"✓ retrieval_states: {len(COMPACT)} states defined")
    print(f"  Citeable: {sorted(CITEABLE)}")
    print(f"  Failed: {sorted(FAILED)}")
