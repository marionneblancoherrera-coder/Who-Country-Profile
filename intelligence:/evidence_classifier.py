"""
evidence_classifier.py
WHO DAK Intelligence Platform — intelligence/evidence_classifier.py

Classifies every field claim with an evidence type and confidence flag.
Reads config/source_hierarchy.yml and config/evidence_rules.yml.

Input  : FieldEvidence (value, source metadata, optional contradiction)
Output : EvidenceClassification (type code, confidence code, flags, notes)
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Optional

import yaml

CONFIG_DIR       = Path(__file__).resolve().parent.parent / "config"
HIERARCHY_PATH   = CONFIG_DIR / "source_hierarchy.yml"
RULES_PATH       = CONFIG_DIR / "evidence_rules.yml"

# ── Evidence type codes (from evidence_rules.yml) ────────────
TYPE_FACT        = "F"
TYPE_INFERENCE   = "INF"
TYPE_HEURISTIC   = "OH"
TYPE_CONTRADICTED = "C"
TYPE_UNRESOLVED  = "U"

# ── Confidence codes (from source_hierarchy.yml) ──────────────
CONF_VERIFIED    = "V"
CONF_VERIFIED_AC = "VA"
CONF_INFERRED    = "I"
CONF_INFERRED_W  = "IW"
CONF_UNKNOWN     = "U"
CONF_CONTRADICTED = "C"

# ── Source type → default confidence mapping ──────────────────
# Derived from source_hierarchy.yml legacy_tier_mapping
_SOURCE_DEFAULT_CONF = {
    "global_normative":               CONF_VERIFIED,
    "peer_reviewed_research":         CONF_VERIFIED_AC,
    "national_government":            CONF_INFERRED,
    "implementation_documentation":   CONF_INFERRED,
    "programme_and_operational_reviews": CONF_INFERRED,
    "grey_literature":                CONF_INFERRED_W,
}

# ── Retrieval states that allow a claim to be cited ───────────
_CITEABLE_STATES = {
    "parsed", "validated", "partially_parsed", "accessible"
}


# ── Data classes ──────────────────────────────────────────────

@dataclass
class FieldEvidence:
    """
    Everything known about a single field retrieval attempt.
    Pass None for optional fields that were not retrieved.
    """
    field_name:      str
    value:           object           # the actual value retrieved

    # Source metadata
    source_type:     str              # from source_hierarchy.yml source_types
    retrieval_state: str              # from source_hierarchy.yml retrieval_states
    source_url:      Optional[str]    = None
    publication_date: Optional[str]   = None   # ISO date string or year
    retrieval_date:   Optional[str]   = None   # ISO date string

    # Contradiction (second source on same field)
    contradicting_value:        Optional[object] = None
    contradicting_source_type:  Optional[str]    = None
    contradicting_source_url:   Optional[str]    = None
    contradicting_dimension:    Optional[str]    = None  # what it measures

    # Type overrides
    is_inference:    bool = False     # set True for derived fields
    is_heuristic:    bool = False     # set True for donor_signals etc.
    heuristic_confidence: Optional[float] = None

    # Country/run modifiers
    fragile_state:   bool = False
    survey_source:   bool = False     # is this from a DHS/MICS survey?


@dataclass
class EvidenceClassification:
    """
    Full evidence classification for one field.
    """
    field_name:        str
    evidence_type:     str    # F | INF | OH | C | U
    confidence_code:   str    # V | VA | I | IW | U | C
    confidence_label:  str
    needs_crosscheck:  bool   # T3 source → mandatory T2 query needed
    penalties_applied: list[str] = field(default_factory=list)
    notes:             list[str] = field(default_factory=list)

    # For contradicted fields
    contradiction_record: Optional[dict] = None

    # Source attribution (for output rendering)
    source_url:       Optional[str] = None
    retrieval_date:   Optional[str] = None
    publication_year: Optional[int] = None


# ── Config loader ─────────────────────────────────────────────

def _load_hierarchy() -> dict:
    with open(HIERARCHY_PATH, encoding="utf-8") as f:
        return yaml.safe_load(f)

def _load_rules() -> dict:
    with open(RULES_PATH, encoding="utf-8") as f:
        return yaml.safe_load(f)

def _parse_year(date_str: Optional[str]) -> Optional[int]:
    if not date_str:
        return None
    try:
        return int(str(date_str)[:4])
    except (ValueError, TypeError):
        return None

def _years_since(date_str: Optional[str]) -> Optional[int]:
    year = _parse_year(date_str)
    if year is None:
        return None
    return date.today().year - year


# ── Main classifier ───────────────────────────────────────────

def classify_field(ev: FieldEvidence) -> EvidenceClassification:
    """
    Classify a single field's evidence type and confidence.
    Applies all modifiers from evidence_rules.yml.
    """
    penalties   = []
    notes       = []
    contradiction_record = None

    # ── Step 1: Unresolvable states → UNRESOLVED ──────────────
    if ev.value is None or ev.retrieval_state not in _CITEABLE_STATES:
        return EvidenceClassification(
            field_name=ev.field_name,
            evidence_type=TYPE_UNRESOLVED,
            confidence_code=CONF_UNKNOWN,
            confidence_label="unknown",
            needs_crosscheck=False,
            notes=[
                f"Retrieval state: {ev.retrieval_state}",
                f"Source URL attempted: {ev.source_url or 'none'}",
            ],
            source_url=ev.source_url,
        )

    # ── Step 2: Contradiction detection ───────────────────────
    has_contradiction = (
        ev.contradicting_value is not None
        and ev.contradicting_source_type in (
            "global_normative", "peer_reviewed_research"
        )
        and ev.source_type in (
            "global_normative", "peer_reviewed_research"
        )
    )
    if has_contradiction:
        contradiction_record = {
            "value_a": ev.value,
            "source_a": ev.source_url,
            "source_type_a": ev.source_type,
            "dimension_a": "primary retrieval",
            "value_b": ev.contradicting_value,
            "source_b": ev.contradicting_source_url,
            "source_type_b": ev.contradicting_source_type,
            "dimension_b": ev.contradicting_dimension or "secondary retrieval",
        }
        return EvidenceClassification(
            field_name=ev.field_name,
            evidence_type=TYPE_CONTRADICTED,
            confidence_code=CONF_CONTRADICTED,
            confidence_label="CONTRADICTED",
            needs_crosscheck=False,
            notes=[
                "Two same-tier sources disagree. Both recorded.",
                "Do not resolve — contradiction is the finding.",
                f"Value A: {ev.value} ({ev.source_type})",
                f"Value B: {ev.contradicting_value} ({ev.contradicting_source_type})",
            ],
            contradiction_record=contradiction_record,
            source_url=ev.source_url,
        )

    # ── Step 3: Determine evidence type ───────────────────────
    if ev.is_heuristic:
        evidence_type = TYPE_HEURISTIC
    elif ev.is_inference:
        evidence_type = TYPE_INFERENCE
    else:
        evidence_type = TYPE_FACT

    # ── Step 4: Base confidence from source type ──────────────
    conf_code = _SOURCE_DEFAULT_CONF.get(ev.source_type, CONF_INFERRED)

    # ── Step 5: Recency penalty ────────────────────────────────
    hierarchy = _load_hierarchy()
    rules     = _load_rules()

    age = _years_since(ev.publication_date)
    if age is not None:
        recency_thresholds = {
            "global_normative":             2,
            "peer_reviewed_research":       3,
            "national_government":          3,
            "implementation_documentation": 2,
            "grey_literature":              1,
        }
        threshold = recency_thresholds.get(ev.source_type, 3)
        if age > threshold:
            conf_code = _downgrade(conf_code)
            notes.append(
                f"Recency: {age} years old (threshold {threshold}) → downgraded"
            )

    # ── Step 6: Survey age modifier ───────────────────────────
    survey_threshold = rules.get("survey_age_modifier", {}).get("threshold_years", 4)
    if ev.survey_source and age and age > survey_threshold:
        conf_code = _downgrade(conf_code)
        penalties.append(f"SURVEY_AGE_WARNING: survey {age} years old (>{survey_threshold})")

    # ── Step 7: Fragile state modifier ─────────────────────────
    if ev.fragile_state:
        conf_code = _downgrade(conf_code)
        penalties.append("FRAGILE_STATE_ESTIMATE: modelled estimate, not direct measurement")

    # ── Step 8: Heuristic confidence override ─────────────────
    if ev.is_heuristic and ev.heuristic_confidence is not None:
        # Map numeric confidence to code
        if ev.heuristic_confidence >= 0.80:
            conf_code = CONF_INFERRED
        elif ev.heuristic_confidence >= 0.60:
            conf_code = CONF_INFERRED
        else:
            conf_code = CONF_INFERRED_W
        notes.append(
            f"Operational heuristic confidence: {ev.heuristic_confidence:.0%} "
            "(verify in B2)"
        )

    # ── Step 9: Cross-check flag ──────────────────────────────
    needs_crosscheck = (ev.source_type == "national_government")
    if needs_crosscheck:
        notes.append(
            "T3 source: mandatory PMC cross-check required before finalising"
        )

    # ── Step 10: Publication year extraction ──────────────────
    pub_year = _parse_year(ev.publication_date)

    label_map = {
        CONF_VERIFIED:    "verified",
        CONF_VERIFIED_AC: "verified-academic",
        CONF_INFERRED:    "inferred",
        CONF_INFERRED_W:  "inferred-weak",
        CONF_UNKNOWN:     "unknown",
        CONF_CONTRADICTED:"CONTRADICTED",
    }

    return EvidenceClassification(
        field_name=ev.field_name,
        evidence_type=evidence_type,
        confidence_code=conf_code,
        confidence_label=label_map.get(conf_code, conf_code),
        needs_crosscheck=needs_crosscheck,
        penalties_applied=penalties,
        notes=notes,
        source_url=ev.source_url,
        retrieval_date=ev.retrieval_date,
        publication_year=pub_year,
    )


def _downgrade(code: str) -> str:
    """Move one step down the confidence ladder."""
    ladder = [CONF_VERIFIED, CONF_VERIFIED_AC, CONF_INFERRED, CONF_INFERRED_W, CONF_UNKNOWN]
    try:
        idx = ladder.index(code)
        return ladder[min(idx + 1, len(ladder) - 1)]
    except ValueError:
        return CONF_INFERRED_W


def classify_many(fields: list[FieldEvidence]) -> list[EvidenceClassification]:
    return [classify_field(f) for f in fields]


def reliability_inputs(classifications: list[EvidenceClassification]) -> dict:
    """
    Aggregate classification results into inputs for reliability_formula.py.
    """
    total = len(classifications)
    if total == 0:
        return {}
    filled  = [c for c in classifications if c.confidence_code != CONF_UNKNOWN]
    t1t2    = [c for c in filled if c.confidence_code in (CONF_VERIFIED, CONF_VERIFIED_AC)]
    recent  = [c for c in filled if c.publication_year
               and (date.today().year - c.publication_year) <= 3]
    no_cont = [c for c in filled if c.confidence_code != CONF_CONTRADICTED]
    penalties = []
    for c in classifications:
        penalties.extend(c.penalties_applied)

    return {
        "total_fields":        total,
        "filled_count":        len(filled),
        "tier1_2_count":       len(t1t2),
        "recent_count":        len(recent),
        "no_contradiction_count": len(no_cont),
        "active_penalties":    list(set(penalties)),
        "crosscheck_needed":   [c.field_name for c in classifications if c.needs_crosscheck],
    }


# ── Tests ─────────────────────────────────────────────────────

def _run_tests() -> None:
    print("=== EVIDENCE CLASSIFIER TESTS ===\n")
    passed = 0
    total  = 0

    # T1: WHO GHO indicator, current → verified (F)
    total += 1
    ev = FieldEvidence(
        field_name="anc4_coverage", value=76,
        source_type="global_normative",
        retrieval_state="parsed",
        source_url="https://ghoapi.azureedge.net/api/RMNCH.ANC_4",
        publication_date="2025", retrieval_date="2026-05-25",
    )
    c = classify_field(ev)
    assert c.evidence_type == TYPE_FACT, f"Expected F, got {c.evidence_type}"
    assert c.confidence_code == CONF_VERIFIED, f"Expected V, got {c.confidence_code}"
    assert c.needs_crosscheck is False
    passed += 1
    print(f"✓ T1 WHO GHO current (2025) → F/V  [{c.evidence_type}/{c.confidence_code}]")

    # T1b: 3-year-old global_normative → correctly downgraded to VA
    total += 1
    ev1b = FieldEvidence(
        field_name="anc4_coverage", value=76,
        source_type="global_normative",
        retrieval_state="parsed",
        publication_date="2023",
    )
    c1b = classify_field(ev1b)
    assert c1b.confidence_code == CONF_VERIFIED_AC,         f"3yr old T1 should downgrade to VA, got {c1b.confidence_code}"
    passed += 1
    print(f"✓ T1 WHO GHO 2023 (3yr) → F/VA  [{c1b.evidence_type}/{c1b.confidence_code}]")

    # T2: Government portal → inferred + crosscheck flag
    total += 1
    ev2 = FieldEvidence(
        field_name="poc_system_name", value="EDUS",
        source_type="national_government",
        retrieval_state="parsed",
        source_url="https://www.ccss.sa.cr/edus",
        publication_date="2024",
    )
    c2 = classify_field(ev2)
    assert c2.evidence_type == TYPE_FACT
    assert c2.confidence_code == CONF_INFERRED
    assert c2.needs_crosscheck is True
    passed += 1
    print(f"✓ T3 gov portal → F/I + crosscheck=True  [{c2.evidence_type}/{c2.confidence_code}]")

    # T3: Stale government source → inferred-weak
    total += 1
    ev3 = FieldEvidence(
        field_name="national_guidelines_year", value=2009,
        source_type="national_government",
        retrieval_state="parsed",
        source_url="https://binasss.sa.cr/protocolos",
        publication_date="2009",
    )
    c3 = classify_field(ev3)
    assert c3.confidence_code == CONF_INFERRED_W, \
        f"Expected IW for stale T3, got {c3.confidence_code}"
    passed += 1
    print(f"✓ Stale T3 (2009) → IW  [{c3.evidence_type}/{c3.confidence_code}]")

    # T4: Contradiction between two T1 sources
    total += 1
    ev4 = FieldEvidence(
        field_name="maternal_mortality_ratio", value=22,
        source_type="global_normative",
        retrieval_state="parsed",
        source_url="https://ghoapi.azureedge.net/api/MDG_0000000026",
        publication_date="2020",
        contradicting_value=24,
        contradicting_source_type="global_normative",
        contradicting_source_url="https://who.int/data/...",
        contradicting_dimension="WHO 2023 model estimate",
    )
    c4 = classify_field(ev4)
    assert c4.evidence_type == TYPE_CONTRADICTED
    assert c4.confidence_code == CONF_CONTRADICTED
    assert c4.contradiction_record is not None
    passed += 1
    print(f"✓ T1 vs T1 contradiction → C/C  [{c4.evidence_type}/{c4.confidence_code}]")

    # T5: Unresolved / js_blocked
    total += 1
    ev5 = FieldEvidence(
        field_name="digital_atlas_entry", value=None,
        source_type="implementation_documentation",
        retrieval_state="js_blocked",
        source_url="https://digitalhealthatlas.org/...",
    )
    c5 = classify_field(ev5)
    assert c5.evidence_type == TYPE_UNRESOLVED
    assert c5.confidence_code == CONF_UNKNOWN
    passed += 1
    print(f"✓ js_blocked → U/U  [{c5.evidence_type}/{c5.confidence_code}]")

    # T6: Operational heuristic (donor signal)
    total += 1
    ev6 = FieldEvidence(
        field_name="expected_hmis", value="DHIS2",
        source_type="global_normative",
        retrieval_state="parsed",
        is_heuristic=True,
        heuristic_confidence=0.82,
    )
    c6 = classify_field(ev6)
    assert c6.evidence_type == TYPE_HEURISTIC
    assert c6.confidence_code == CONF_INFERRED
    assert "82%" in " ".join(c6.notes)
    passed += 1
    print(f"✓ Heuristic GF→DHIS2 (0.82) → OH/I  [{c6.evidence_type}/{c6.confidence_code}]")

    # T7: Fragile state modifier
    total += 1
    ev7 = FieldEvidence(
        field_name="anc4_coverage", value=55,
        source_type="global_normative",
        retrieval_state="parsed",
        publication_date="2023",
        fragile_state=True,
    )
    c7 = classify_field(ev7)
    assert c7.confidence_code in (CONF_VERIFIED_AC, CONF_INFERRED), \
        f"Fragile state should downgrade V to VA or I, got {c7.confidence_code}"
    assert any("FRAGILE" in p for p in c7.penalties_applied)
    passed += 1
    print(f"✓ Fragile state downgrade: V→{c7.confidence_code}  {c7.penalties_applied}")

    # T8: Survey age warning
    total += 1
    ev8 = FieldEvidence(
        field_name="anc4_coverage", value=71,
        source_type="global_normative",
        retrieval_state="parsed",
        publication_date="2018",
        survey_source=True,
    )
    c8 = classify_field(ev8)
    assert any("SURVEY_AGE" in p for p in c8.penalties_applied)
    passed += 1
    print(f"✓ Survey age warning (2018): {c8.penalties_applied}")

    # T9: reliability_inputs aggregation
    total += 1
    batch = [
        FieldEvidence("f1", 76,  "global_normative",   "parsed", publication_date="2023"),
        FieldEvidence("f2", 22,  "peer_reviewed_research", "parsed", publication_date="2024"),
        FieldEvidence("f3", "EDUS", "national_government", "parsed", publication_date="2024"),
        FieldEvidence("f4", None, "implementation_documentation", "js_blocked"),
    ]
    results = classify_many(batch)
    agg = reliability_inputs(results)
    assert agg["total_fields"]  == 4
    assert agg["filled_count"]  == 3    # f4 is unknown
    assert agg["tier1_2_count"] == 2    # f1 + f2
    assert "f3" in agg["crosscheck_needed"]
    passed += 1
    print(f"✓ reliability_inputs: total=4 filled=3 t1t2=2 crosscheck={agg['crosscheck_needed']}")

    print(f"\nResult: {passed}/{total} correct")


if __name__ == "__main__":
    _run_tests()
