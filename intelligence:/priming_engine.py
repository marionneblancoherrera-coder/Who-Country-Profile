"""
priming_engine.py
WHO DAK Intelligence Platform — intelligence/priming_engine.py

Generates Block 2 priming signals from completed Block 1 output.
Reads config/domain_indicators.yml (b2_routing_signals section).

Input  : B1FieldSet + ClassifierOutput
Output : PrimingResult (fired signals, source strategy adjustments, notes)

The priming result is recorded in run_output as b1_priming_output.json
so every B2 decision is auditable.
"""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import yaml

CONFIG_DIR      = Path(__file__).resolve().parent.parent / "config"
INDICATORS_PATH = CONFIG_DIR / "domain_indicators.yml"
DONOR_PATH      = CONFIG_DIR / "donor_signals.yml"


# ── Data classes ──────────────────────────────────────────────

@dataclass
class B1Field:
    """Single Block 1 output field with value and evidence type."""
    name:            str
    value:           object
    evidence_type:   str    # F | INF | OH | C | U
    confidence_code: str    # V | VA | I | IW | U | C
    source_url:      Optional[str] = None


@dataclass
class FiredSignal:
    """A routing signal that evaluated to True."""
    name:        str
    trigger:     str
    instruction: str
    b1_value:    object         # the B1 field value that triggered it
    b1_field:    str            # which B1 field triggered it


@dataclass
class PrimingResult:
    """
    Complete priming output from B1 → B2.
    Recorded in run_output/b1_priming_output.json.
    """
    dak_domain:       str
    country_iso3:     str
    category_code:    str

    fired_signals:    list[FiredSignal] = field(default_factory=list)
    donor_predictions: list[dict]       = field(default_factory=list)

    # Derived instructions for B2
    dak_use_case:          str = "standard"  # standard | quality_std | access_gap
    prioritize_facility_level: list[str] = field(default_factory=list)
    expected_systems:      list[str] = field(default_factory=list)
    expected_system_confidence: dict = field(default_factory=dict)
    risk_flags_to_anticipate: list[str] = field(default_factory=list)
    source_strategy_notes: list[str] = field(default_factory=list)

    b1_score:              float = 0.0
    b2_gate_passed:        bool  = True
    b2_gate_reason:        str   = ""


# ── Loader ────────────────────────────────────────────────────

def _load_indicators() -> dict:
    with open(INDICATORS_PATH, encoding="utf-8") as f:
        return yaml.safe_load(f)

def _load_donors() -> dict:
    with open(DONOR_PATH, encoding="utf-8") as f:
        return yaml.safe_load(f)

def _get(fields: dict[str, B1Field], name: str) -> Optional[B1Field]:
    return fields.get(name)

def _val(fields: dict[str, B1Field], name: str, default=None):
    f = fields.get(name)
    return f.value if f else default


# ── Main engine ───────────────────────────────────────────────

def generate_priming(
    b1_fields:   dict[str, B1Field],
    dak_domain:  str,
    iso3:        str,
    category_code: str,
    b1_score:    float,
    classifier_priming: dict,
) -> PrimingResult:
    """
    Evaluate all B2 routing signals against B1 output.
    Combine with classifier priming from classifier.py.
    """
    result = PrimingResult(
        dak_domain=dak_domain,
        country_iso3=iso3,
        category_code=category_code,
        b1_score=b1_score,
    )

    # ── Gate check ────────────────────────────────────────────
    if b1_score < 0.50:
        result.b2_gate_passed = False
        result.b2_gate_reason = (
            f"B1 reliability score {b1_score:.2f} < 0.50 threshold. "
            "Block 2 cannot execute. Output: skeleton profile + gap map."
        )
        return result

    # ── Load routing signals ──────────────────────────────────
    data    = _load_indicators()
    signals = data.get("b2_routing_signals", {})

    # ── Evaluate each signal ──────────────────────────────────
    for sig_name, sig in signals.items():
        trigger     = sig.get("trigger", "")
        instruction = sig.get("instruction", "")
        fired, b1_field, b1_val = _evaluate_trigger(
            trigger, b1_fields, dak_domain
        )
        if fired:
            result.fired_signals.append(FiredSignal(
                name=sig_name,
                trigger=trigger,
                instruction=instruction,
                b1_value=b1_val,
                b1_field=b1_field,
            ))
            _apply_signal(sig_name, instruction, result)

    # ── Donor predictions from classifier priming ─────────────
    _apply_donor_predictions(classifier_priming, dak_domain, result)

    # ── Infrastructure focus ──────────────────────────────────
    _apply_infrastructure_focus(data, dak_domain, b1_fields, result)

    # ── Source strategy from category ─────────────────────────
    _apply_category_strategy(category_code, result)

    return result


def _evaluate_trigger(
    trigger: str,
    fields:  dict[str, B1Field],
    domain:  str,
) -> tuple[bool, str, object]:
    """
    Evaluate a trigger string against B1 fields.
    Returns (fired, field_name, field_value).
    """
    trigger = trigger.strip()

    # domain filter
    if "dak_domain IN" in trigger:
        if domain not in trigger:
            return False, "", None

    # Numeric comparisons
    for field_name in [
        "domain_coverage_pct", "physician_density",
        "nurse_midwife_density", "national_guidelines_year",
        "fragmentation_score",
    ]:
        val = _val(fields, field_name)
        if val is None:
            continue
        if field_name in trigger:
            try:
                if "< 50" in trigger and float(val) < 50:
                    return True, field_name, val
                if "> 85" in trigger and float(val) > 85:
                    return True, field_name, val
                if "< 0.2" in trigger and float(val) < 0.2:
                    return True, field_name, val
                if "< 2.0" in trigger and float(val) < 2.0:
                    return True, field_name, val
                if "< current_year - 3" in trigger:
                    from datetime import date as d
                    if int(val) < d.today().year - 3:
                        return True, field_name, val
                if "> 5" in trigger and float(val) > 5:
                    return True, field_name, val
            except (TypeError, ValueError):
                pass

    # Boolean checks
    for bool_field, bool_trigger in [
        ("active_gf_grant",            "gf_grant_active = true"),
        ("pepfar_active",              "pepfar_active = true"),
        ("gavi_eligible",              "gavi_eligible = true"),
        ("quality_gap_evidence",       "quality_gap_evidence = true"),
        ("governance_model_federal",   'governance_model = federal'),
    ]:
        if bool_trigger in trigger:
            val = _val(fields, bool_field)
            if val is True:
                return True, bool_field, val

    return False, "", None


def _apply_signal(name: str, instruction: str, result: PrimingResult) -> None:
    short = instruction.strip()[:120]

    if name == "low_coverage":
        result.prioritize_facility_level = ["primary", "community"]
        result.source_strategy_notes.append(
            "Coverage <50%: prioritise primary care systems in B2"
        )
    elif name == "quality_gap_detected":
        result.dak_use_case = "quality_standardization"
        result.source_strategy_notes.append(
            "Quality gap detected: DAK use case = quality standardisation"
        )
        result.risk_flags_to_anticipate.append("QUALITY_COVERAGE_GAP")
    elif name == "low_operator_capacity":
        result.risk_flags_to_anticipate.append("RISK_LOW_OPERATOR_CAPACITY")
        result.source_strategy_notes.append(
            "Low workforce density: prefer low-complexity digital systems"
        )
    elif name == "donor_gf_active":
        if "DHIS2" not in result.expected_systems:
            result.expected_systems.append("DHIS2")
            result.expected_system_confidence["DHIS2"] = 0.82
    elif name == "donor_pepfar_active":
        if "OpenMRS" not in result.expected_systems:
            result.expected_systems.append("OpenMRS")
            result.expected_system_confidence["OpenMRS"] = 0.68
        if "DATIM" not in result.expected_systems:
            result.expected_systems.append("DATIM")
            result.expected_system_confidence["DATIM"] = 0.88
    elif name == "donor_gavi_active":
        if "DHIS2_immunization_tracker" not in result.expected_systems:
            result.expected_systems.append("DHIS2_immunization_tracker")
            result.expected_system_confidence["DHIS2_immunization_tracker"] = 0.70
    elif name == "decentralised_system":
        result.risk_flags_to_anticipate.append("RISK_FRAGMENTATION")
        result.source_strategy_notes.append(
            "Decentralised governance: anticipate fragmentation_index > 5"
        )
    elif name == "guidelines_outdated":
        result.risk_flags_to_anticipate.append("GUIDELINES_OUTDATED")
        result.source_strategy_notes.append(
            "Guidelines outdated: content risk for Step 2 of DAK localisation"
        )


def _apply_donor_predictions(
    classifier_priming: dict,
    domain: str,
    result: PrimingResult,
) -> None:
    """Merge classifier-level donor predictions into result."""
    if classifier_priming.get("expect_dhis2"):
        conf = classifier_priming.get("expect_dhis2_confidence", 0.82)
        if "DHIS2" not in result.expected_systems:
            result.expected_systems.append("DHIS2")
            result.expected_system_confidence["DHIS2"] = conf
        result.donor_predictions.append({
            "system": "DHIS2",
            "confidence": conf,
            "source": "classifier_priming"
        })

    if classifier_priming.get("expect_openmrs_hiv") and domain == "HIV":
        conf = classifier_priming.get("expect_openmrs_confidence", 0.68)
        if "OpenMRS" not in result.expected_systems:
            result.expected_systems.append("OpenMRS")
            result.expected_system_confidence["OpenMRS"] = conf

    if classifier_priming.get("expect_openlmis") and domain == "Immunization":
        if "OpenLMIS" not in result.expected_systems:
            result.expected_systems.append("OpenLMIS")
            result.expected_system_confidence["OpenLMIS"] = 0.62

    if classifier_priming.get("adoption_gap_likely"):
        result.risk_flags_to_anticipate.append("RISK_ADOPTION_GAP")
        result.source_strategy_notes.append(
            "HQ_PARADOX: official sources suppress real adoption — "
            "mandatory Tier 5 + PMC search"
        )

    if classifier_priming.get("feasibility_note_required"):
        result.risk_flags_to_anticipate.append("LOCALIZATION_FEASIBILITY_FLAG")

    if classifier_priming.get("risk_vendor_is_government"):
        result.risk_flags_to_anticipate.append("RISK_VENDOR_IS_GOVERNMENT")

    if classifier_priming.get("interoperability_gap_possible"):
        result.risk_flags_to_anticipate.append("RISK_INTEROPERABILITY_GAP")

    if classifier_priming.get("active_transition_likely"):
        result.risk_flags_to_anticipate.append("RISK_TRANSITION")

    # Merge source notes
    if classifier_priming.get("source_note"):
        result.source_strategy_notes.append(classifier_priming["source_note"])
    if classifier_priming.get("critical_note"):
        result.source_strategy_notes.append(classifier_priming["critical_note"])


def _apply_infrastructure_focus(
    data: dict,
    domain: str,
    fields: dict[str, B1Field],
    result: PrimingResult,
) -> None:
    """Set facility-level focus from domain infrastructure definition."""
    if not result.prioritize_facility_level:  # not already set by low_coverage
        infra = (
            data.get("domain_indicator_sets", {})
                .get(domain, {})
                .get("infrastructure_focus", {})
        )
        levels = infra.get("facility_levels", [])
        if levels:
            result.prioritize_facility_level = levels


def _apply_category_strategy(category_code: str, result: PrimingResult) -> None:
    strategies = {
        "TS": "OpenHIE wiki + Global Fund portfolio. WHO Atlas js_blocked — use fallback.",
        "CE": "PAHO + IDB. National EHR absent from WHO registries.",
        "FR": "WHO EURO + ECDC. Run 'broken/failure' PMC query.",
        "SV": "PMC local academic papers. WHO registries will be empty.",
        "HQ": "National eHealth agency + GDHI + PMC adoption query. T5 for real adoption.",
        "MX": "Use full source hierarchy.",
    }
    note = strategies.get(category_code)
    if note and note not in result.source_strategy_notes:
        result.source_strategy_notes.append(note)


# ── Serialiser ────────────────────────────────────────────────

def to_dict(result: PrimingResult) -> dict:
    return {
        "dak_domain":      result.dak_domain,
        "country_iso3":    result.country_iso3,
        "category_code":   result.category_code,
        "b1_score":        result.b1_score,
        "b2_gate_passed":  result.b2_gate_passed,
        "b2_gate_reason":  result.b2_gate_reason,
        "dak_use_case":    result.dak_use_case,
        "fired_signals":   [
            {"name": s.name, "b1_field": s.b1_field,
             "b1_value": s.b1_value, "instruction": s.instruction[:80]}
            for s in result.fired_signals
        ],
        "expected_systems":              result.expected_systems,
        "expected_system_confidence":    result.expected_system_confidence,
        "risk_flags_to_anticipate":      result.risk_flags_to_anticipate,
        "prioritize_facility_level":     result.prioritize_facility_level,
        "source_strategy_notes":         result.source_strategy_notes,
        "donor_predictions":             result.donor_predictions,
    }


# ── Tests ─────────────────────────────────────────────────────

def _run_tests() -> None:
    print("=== PRIMING ENGINE TESTS ===\n")
    passed = 0
    total  = 0

    def make_field(name, value, conf="V"):
        return B1Field(name=name, value=value,
                       evidence_type="F", confidence_code=conf)

    # ── Test 1: Zambia ANC — TARGET_STANDARD with GF grant ────
    total += 1
    zambia_b1 = {
        "domain_coverage_pct":   make_field("domain_coverage_pct", 76),
        "active_gf_grant":       make_field("active_gf_grant", True),
        "gavi_eligible":         make_field("gavi_eligible", True),
        "physician_density":     make_field("physician_density", 0.17),
        "national_guidelines_year": make_field("national_guidelines_year", 2021),
    }
    zambia_classifier_priming = {
        "expect_dhis2": True,
        "expect_dhis2_confidence": 0.82,
        "expect_openlmis": True,
        "critical_note": "Official MoH sources will not document integration gaps.",
    }
    r1 = generate_priming(zambia_b1, "ANC", "ZMB", "TS", 0.74,
                          zambia_classifier_priming)
    assert r1.b2_gate_passed is True
    assert "DHIS2" in r1.expected_systems
    assert "RISK_LOW_OPERATOR_CAPACITY" in r1.risk_flags_to_anticipate
    assert r1.dak_use_case == "standard"
    assert any("integration" in n.lower() for n in r1.source_strategy_notes)
    passed += 1
    print(f"✓ Zambia ANC: gate=✓ systems={r1.expected_systems} "
          f"flags={r1.risk_flags_to_anticipate}")

    # ── Test 2: Costa Rica ANC — CENTRALIZED, quality gap ─────
    total += 1
    cr_b1 = {
        "domain_coverage_pct":      make_field("domain_coverage_pct", 99),
        "quality_gap_evidence":     make_field("quality_gap_evidence", True),
        "active_gf_grant":          make_field("active_gf_grant", False),
        "national_guidelines_year": make_field("national_guidelines_year", 2009),
    }
    cr_priming = {
        "risk_vendor_is_government": True,
        "interoperability_gap_possible": True,
        "source_note": "PAHO + IDB. National EHR absent from WHO registries.",
    }
    r2 = generate_priming(cr_b1, "ANC", "CRI", "CE", 0.77, cr_priming)
    assert r2.b2_gate_passed is True
    assert r2.dak_use_case == "quality_standardization"
    assert "GUIDELINES_OUTDATED" in r2.risk_flags_to_anticipate
    assert "RISK_VENDOR_IS_GOVERNMENT" in r2.risk_flags_to_anticipate
    assert "RISK_INTEROPERABILITY_GAP" in r2.risk_flags_to_anticipate
    passed += 1
    print(f"✓ Costa Rica ANC: use_case={r2.dak_use_case} "
          f"flags={r2.risk_flags_to_anticipate}")

    # ── Test 3: Switzerland — HQ_PARADOX ──────────────────────
    total += 1
    ch_b1 = {
        "domain_coverage_pct": make_field("domain_coverage_pct", 99),
        "active_gf_grant":     make_field("active_gf_grant", False),
    }
    ch_priming = {
        "adoption_gap_likely": True,
        "feasibility_note_required": True,
        "source_note": "Official eHealth agency suppresses real adoption data.",
    }
    r3 = generate_priming(ch_b1, "ANC", "CHE", "HQ", 0.80, ch_priming)
    assert r3.b2_gate_passed is True
    assert "RISK_ADOPTION_GAP" in r3.risk_flags_to_anticipate
    assert "LOCALIZATION_FEASIBILITY_FLAG" in r3.risk_flags_to_anticipate
    assert any("adoption" in n.lower() for n in r3.source_strategy_notes)
    passed += 1
    print(f"✓ Switzerland HQ: flags={r3.risk_flags_to_anticipate}")

    # ── Test 4: B1 gate — score too low ───────────────────────
    total += 1
    r4 = generate_priming({}, "ANC", "YEM", "TS", 0.38, {})
    assert r4.b2_gate_passed is False
    assert "0.38" in r4.b2_gate_reason
    assert len(r4.fired_signals) == 0
    passed += 1
    print(f"✓ Yemen gate blocked (score=0.38): {r4.b2_gate_reason[:60]}...")

    # ── Test 5: Serialisation ─────────────────────────────────
    total += 1
    d = to_dict(r2)
    assert d["dak_use_case"] == "quality_standardization"
    assert isinstance(d["fired_signals"], list)
    assert isinstance(d["expected_system_confidence"], dict)
    json.dumps(d)   # must be JSON-serialisable
    passed += 1
    print(f"✓ to_dict serialisable: {list(d.keys())}")

    # ── Test 6: PEPFAR + HIV priming ──────────────────────────
    total += 1
    hiv_b1 = {
        "pepfar_active":       make_field("pepfar_active", True),
        "active_gf_grant":     make_field("active_gf_grant", True),
        "domain_coverage_pct": make_field("domain_coverage_pct", 72),
    }
    hiv_priming = {
        "expect_openmrs_hiv": True,
        "expect_openmrs_confidence": 0.68,
    }
    r6 = generate_priming(hiv_b1, "HIV", "KEN", "TS", 0.71, hiv_priming)
    assert "DHIS2" in r6.expected_systems
    assert "OpenMRS" in r6.expected_systems
    assert "DATIM" in r6.expected_systems
    assert r6.expected_system_confidence["DATIM"] == 0.88
    passed += 1
    print(f"✓ PEPFAR+HIV: systems={r6.expected_systems} "
          f"conf={r6.expected_system_confidence}")

    print(f"\nResult: {passed}/{total} correct")

    print("\n=== PRIMING SUMMARY: Costa Rica ANC ===")
    for k, v in to_dict(r2).items():
        if v and v not in ([], {}, "", "standard", True, 0.77):
            print(f"  {k}: {v}")


if __name__ == "__main__":
    _run_tests()
