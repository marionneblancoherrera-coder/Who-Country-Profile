"""
classifier.py
WHO DAK Intelligence Platform — intelligence/classifier.py

Deterministic country classifier. Runs before any LLM call.
Reads config/country_taxonomy.yml exclusively.
No business logic lives in this file — only in the config.

Input  : ClassifierInput (structural signals about the country)
Output : ClassifierOutput (category, profile, priming, confidence)

Same input → same output. Always.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import yaml

# ── Config path ───────────────────────────────────────────────
CONFIG_DIR   = Path(__file__).resolve().parent.parent / "config"
TAXONOMY_PATH = CONFIG_DIR / "country_taxonomy.yml"

# ── Known structural sets ─────────────────────────────────────
# Source: country_taxonomy.yml confirmed_examples + WHO/UN HQ list.
# Update these sets when new confirmed examples are added to taxonomy.
# Do NOT add classification logic here — logic lives in the decision tree.

_UN_WHO_HQ_ISO2 = frozenset({
    "CH",   # Switzerland — WHO HQ Geneva
    "US",   # USA — UN New York, PAHO Washington
    "KE",   # Kenya — WHO AFRO, UN Nairobi
    "DK",   # Denmark — WHO EURO Copenhagen
    "AT",   # Austria — UN Vienna
    "BE",   # Belgium — WHO EURO Brussels
    "NL",   # Netherlands — OPCW, ICJ The Hague
})

_SOVEREIGN_ISO2 = frozenset({
    "CN",   # China — confirmed example
    "IN",   # India (national level)
    "RU",   # Russia
    "BR",   # Brazil (national SUS level)
    "SA",   # Saudi Arabia
    "AE",   # UAE
    "TR",   # Turkey
    "EG",   # Egypt
})

_FRAGMENTED_ISO2 = frozenset({
    "IT",   # Italy — confirmed example
    "DE",   # Germany (16 Länder)
    "ES",   # Spain (17 autonomous communities)
    "FR",   # France (18 regions)
    "BE",   # Belgium (3 communities — also HQ)
    "AT",   # Austria (9 states — also HQ)
    "SE",   # Sweden
    "NO",   # Norway
    "AU",   # Australia
    "CA",   # Canada
})

# ── Data classes ──────────────────────────────────────────────

@dataclass
class ClassifierInput:
    """
    Structural signals about the country.
    All Optional fields default to None — classifier handles missing data.
    Donor fields are from fast B1 fetches (no LLM needed).
    Governance fields may come from B1 retrieval or domain knowledge.
    """
    iso2: str
    iso3: str
    country_name: str
    income_level: str   # "low" | "lower-middle" | "upper-middle" | "high"

    # Donor signals (fetched from portfolio pages before classification)
    active_gf_grant:    Optional[bool] = None
    pepfar_active:      Optional[bool] = None
    gavi_eligible:      Optional[bool] = None
    world_bank_active:  Optional[bool] = None
    eu_pnrr_active:     Optional[bool] = None

    # Structural signals (from B1 or domain knowledge)
    governance_model:                 Optional[str]   = None  # centralized/federal/hybrid
    digital_architecture:             Optional[str]   = None  # global_goods/proprietary/hybrid
    fragmentation_score:              Optional[float] = None
    international_organisation_host:  Optional[bool]  = None
    source_sovereignty_restriction:   Optional[bool]  = None


@dataclass
class ClassifierOutput:
    """
    Classification result with full reasoning chain.
    """
    category_code:        str          # HQ | SV | FR | CE | TS | MX
    category_label:       str
    operational_profile:  str          # from taxonomy derived_operational_profiles
    confidence:           str          # high | medium | low
    reasoning:            str
    localization_feasibility_flag: bool
    b2_priming:           dict = field(default_factory=dict)
    primary_source_strategy: str = ""


# ── Taxonomy loader ───────────────────────────────────────────

def _load_taxonomy() -> dict:
    if not TAXONOMY_PATH.exists():
        raise FileNotFoundError(
            f"country_taxonomy.yml not found at {TAXONOMY_PATH}. "
            "Run from repository root or set CONFIG_DIR correctly."
        )
    with open(TAXONOMY_PATH, encoding="utf-8") as f:
        return yaml.safe_load(f)


def _get_profile_map(taxonomy: dict) -> dict:
    """Extract derived_operational_profiles from taxonomy."""
    return taxonomy.get("derived_operational_profiles", {}).get("mapping_rules", {})


# ── Decision tree ─────────────────────────────────────────────

def classify(inp: ClassifierInput) -> ClassifierOutput:
    """
    Apply decision tree in strict priority order.
    First matching rule wins. Logic is documented in
    country_taxonomy.yml decision tree order.
    """
    taxonomy = _load_taxonomy()
    iso2 = inp.iso2.upper()

    # ── Rule 1: WHO/UN headquarters host ─────────────────────
    is_hq = (
        iso2 in _UN_WHO_HQ_ISO2
        or inp.international_organisation_host is True
    )
    if is_hq:
        return ClassifierOutput(
            category_code="HQ",
            category_label="WHO/UN Headquarters Paradox",
            operational_profile="PROFILE_FEDERAL_FRAGMENTED",
            confidence="high",
            reasoning=(
                f"{inp.country_name} ({iso2}) hosts a WHO or major UN headquarters. "
                "Standard DAK localization does not apply. "
                "Activation: iso2 in UN_WHO_HQ set or "
                "international_organisation_host=True."
            ),
            localization_feasibility_flag=True,
            b2_priming=_hq_priming(inp),
            primary_source_strategy=(
                "National eHealth agency + GDHI + PMC adoption barriers query. "
                "Official sources will suppress real adoption data. "
                "Mandatory Tier 5 search for real adoption figures."
            ),
        )

    # ── Rule 2: Sovereign digital ecosystem ──────────────────
    is_sovereign = (
        iso2 in _SOVEREIGN_ISO2
        or inp.source_sovereignty_restriction is True
        or (
            inp.digital_architecture == "proprietary"
            and not _any_donor(inp)
            and inp.income_level in ("upper-middle", "high")
            and inp.governance_model == "centralized"
        )
    )
    if is_sovereign:
        return ClassifierOutput(
            category_code="SV",
            category_label="State-Owned Sovereign Digital Health Ecosystem",
            operational_profile="PROFILE_SOVEREIGN_NATIONAL",
            confidence="high" if iso2 in _SOVEREIGN_ISO2 else "medium",
            reasoning=(
                f"{inp.country_name} ({iso2}) classified as SOVEREIGN. "
                f"Activation: iso2 in sovereign set={iso2 in _SOVEREIGN_ISO2}, "
                f"sovereignty_restriction={inp.source_sovereignty_restriction}."
            ),
            localization_feasibility_flag=True,
            b2_priming=_sovereign_priming(inp),
            primary_source_strategy=(
                "PMC English-language papers from local academic institutions. "
                "WHO GIDH reports. National health commission English documents. "
                "WHO registries will not contain national systems."
            ),
        )

    # ── Rule 3: High-income regionally fragmented ─────────────
    is_fragmented = (
        iso2 in _FRAGMENTED_ISO2
        or inp.governance_model == "federal"
        or (
            inp.fragmentation_score is not None
            and inp.fragmentation_score > 6.0
        )
        or (
            inp.governance_model == "hybrid"
            and inp.income_level == "high"
        )
    )
    if is_fragmented:
        return ClassifierOutput(
            category_code="FR",
            category_label="High-Income Regionally Fragmented System",
            operational_profile="PROFILE_FEDERAL_FRAGMENTED",
            confidence="high" if iso2 in _FRAGMENTED_ISO2 else "medium",
            reasoning=(
                f"{inp.country_name} ({iso2}) classified as FRAGMENTED. "
                f"Activation: iso2 in fragmented set={iso2 in _FRAGMENTED_ISO2}, "
                f"governance={inp.governance_model}, "
                f"fragmentation_score={inp.fragmentation_score}."
            ),
            localization_feasibility_flag=False,
            b2_priming=_fragmented_priming(inp),
            primary_source_strategy=(
                "WHO EURO Health Observatory + ECDC country profile. "
                "Official national EHR portal. "
                "PMC fragmentation and interoperability queries — "
                "run 'broken/failure' query to surface what official sources suppress."
            ),
        )

    # ── Rule 4: Centralized national system ──────────────────
    is_centralized = (
        inp.income_level in ("upper-middle", "high")
        and not _any_donor(inp)
        and inp.governance_model in ("centralized", None)
    )
    if is_centralized:
        return ClassifierOutput(
            category_code="CE",
            category_label="Centralized National Health System",
            operational_profile="PROFILE_SOVEREIGN_NATIONAL",
            confidence="medium",
            reasoning=(
                f"{inp.country_name} ({iso2}) classified as CENTRALIZED. "
                f"Activation: income={inp.income_level}, "
                f"no_external_donors={not _any_donor(inp)}, "
                f"governance={inp.governance_model}. "
                "Confidence medium — centralized classification requires B1 confirmation."
            ),
            localization_feasibility_flag=False,
            b2_priming=_centralized_priming(inp),
            primary_source_strategy=(
                "PAHO/OPS country page + IDB publications. "
                "WHO Digital Health Atlas will NOT contain national system. "
                "Exemplars.health for real-world implementation evidence."
            ),
        )

    # ── Rule 5: Standard DAK target ───────────────────────────
    is_target_standard = (
        inp.income_level in ("low", "lower-middle")
        and _any_donor(inp)
    )
    if is_target_standard:
        return ClassifierOutput(
            category_code="TS",
            category_label="Standard DAK Localization Target",
            operational_profile="PROFILE_DONOR_GLOBAL_GOODS",
            confidence="high",
            reasoning=(
                f"{inp.country_name} ({iso2}) classified as TARGET_STANDARD. "
                f"Activation: income={inp.income_level}, "
                f"gf={inp.active_gf_grant}, "
                f"pepfar={inp.pepfar_active}, "
                f"gavi={inp.gavi_eligible}."
            ),
            localization_feasibility_flag=False,
            b2_priming=_standard_priming(inp),
            primary_source_strategy=(
                "OpenHIE country wiki (check last-edited date). "
                "Global Fund portfolio page. "
                "Digital Square global goods guidebook. "
                "DHIS2 in-action. PATH resources. "
                "CRITICAL: official sources will omit integration gaps — "
                "mandatory PMC cross-check."
            ),
        )

    # ── Rule 6: Mixed / ambiguous ─────────────────────────────
    return ClassifierOutput(
        category_code="MX",
        category_label="Mixed or Ambiguous Classification",
        operational_profile="MIXED",
        confidence="low",
        reasoning=(
            f"{inp.country_name} ({iso2}) could not be confidently classified. "
            f"income={inp.income_level}, donors={_any_donor(inp)}, "
            f"governance={inp.governance_model}. "
            "Apply full source hierarchy. Flag ambiguity in output."
        ),
        localization_feasibility_flag=False,
        b2_priming={"note": "Use full source hierarchy. Flag classification ambiguity."},
        primary_source_strategy="Apply all source categories. Document ambiguity.",
    )


# ── Priming generators ────────────────────────────────────────
# Each generates B2 signals based on B1 context.
# Logic derives from donor_signals.yml and domain_indicators.yml.

def _hq_priming(inp: ClassifierInput) -> dict:
    return {
        "expect_global_goods": False,
        "expect_fragmentation": True,
        "feasibility_note_required": True,
        "adoption_gap_likely": True,
        "source_note": (
            "Official eHealth agency will report legal progress. "
            "Real adoption data requires PMC + Tier 5 search."
        ),
    }

def _sovereign_priming(inp: ClassifierInput) -> dict:
    return {
        "expect_global_goods": False,
        "expect_data_sovereignty_barrier": True,
        "feasibility_note_required": True,
        "best_english_sources": "PMC papers from local academic institutions",
        "source_note": (
            "National system absent from WHO registries. "
            "PMC is primary discovery source."
        ),
    }

def _fragmented_priming(inp: ClassifierInput) -> dict:
    p = {
        "expect_global_goods": False,
        "expect_fragmentation_high": True,
        "governance_barrier_likely": True,
    }
    if inp.eu_pnrr_active:
        p["active_transition_likely"] = True
        p["fhir_layer_emerging"] = True
        p["source_note"] = (
            "EU PNRR active → system likely in FHIR transition. "
            "DAK integration target may be the new FHIR layer."
        )
    else:
        p["source_note"] = (
            "Run 'broken/failure' PMC query — official sources "
            "suppress interoperability failures."
        )
    return p

def _centralized_priming(inp: ClassifierInput) -> dict:
    return {
        "expect_global_goods": False,
        "expect_centralized_system": True,
        "risk_vendor_is_government": True,
        "interoperability_gap_possible": True,
        "source_note": (
            "National EHR likely absent from WHO Digital Health Atlas. "
            "Use PAHO and IDB as primary discovery sources."
        ),
    }

def _standard_priming(inp: ClassifierInput) -> dict:
    p = {}
    if inp.active_gf_grant:
        p["expect_dhis2"] = True
        p["expect_dhis2_confidence"] = 0.82
    if inp.pepfar_active:
        p["expect_openmrs_hiv"] = True
        p["expect_openmrs_confidence"] = 0.68
    if inp.gavi_eligible:
        p["expect_openlmis"] = True
        p["expect_cold_chain_digital"] = True
    p["critical_note"] = (
        "Official MoH sources will not document integration gaps. "
        "PMC cross-check mandatory."
    )
    return p

def _any_donor(inp: ClassifierInput) -> bool:
    return any([
        inp.active_gf_grant,
        inp.pepfar_active,
        inp.gavi_eligible,
        inp.world_bank_active,
    ])


# ── B1 refinement ─────────────────────────────────────────────

def refine_with_b1(
    initial: ClassifierOutput,
    b1_output: dict,
) -> ClassifierOutput:
    """
    Optional second-pass refinement using completed B1 signals.
    Updates priming based on actual B1 findings.
    Does not change the category code — only enriches priming.
    """
    priming = dict(initial.b2_priming)

    coverage = b1_output.get("domain_coverage_pct")
    if coverage is not None and coverage < 50:
        priming["prioritize_primary_care"] = True
        priming["deprioritize_hospital_emr"] = True

    nurse_density = b1_output.get("nurse_midwife_density")
    if nurse_density is not None and nurse_density < 2.0:
        priming["risk_low_operator_capacity"] = True
        priming["prefer_low_complexity_systems"] = True

    if not b1_output.get("national_guidelines_current", True):
        priming["guidelines_outdated"] = True
        priming["content_risk"] = True

    quality_gap = b1_output.get("quality_gap_evidence")
    if quality_gap and coverage and coverage > 85:
        priming["dak_use_case"] = "quality_standardization"

    initial.b2_priming = priming
    return initial


# ── CLI ───────────────────────────────────────────────────────

def _run_tests() -> None:
    """5-country validation + bonus cases."""
    test_cases = [
        # (country, iso2, iso3, income, gf, pepfar, gavi, gov, expected_code)
        ("Switzerland",  "CH", "CHE", "high",          False, False, False, "federal",     "HQ"),
        ("China",        "CN", "CHN", "upper-middle",  False, False, False, "centralized", "SV"),
        ("Italy",        "IT", "ITA", "high",          False, False, False, "federal",     "FR"),
        ("Costa Rica",   "CR", "CRI", "upper-middle",  False, False, False, "centralized", "CE"),
        ("Zambia",       "ZM", "ZMB", "lower-middle",  True,  False, True,  "hybrid",      "TS"),
        # Bonus
        ("Germany",      "DE", "DEU", "high",          False, False, False, "federal",     "FR"),
        ("Ethiopia",     "ET", "ETH", "low",           True,  False, True,  "hybrid",      "TS"),
        ("Denmark",      "DK", "DNK", "high",          False, False, False, "federal",     "HQ"),
        ("Brazil",       "BR", "BRA", "upper-middle",  False, False, False, "centralized", "SV"),
        ("Rwanda",       "RW", "RWA", "low",           True,  False, True,  "centralized", "TS"),
        ("France",       "FR", "FRA", "high",          False, False, False, "federal",     "FR"),
        ("Uruguay",      "UY", "URY", "upper-middle",  False, False, False, "centralized", "CE"),
    ]

    passed = 0
    print("=== CLASSIFIER TEST — 5-country validation + bonus ===\n")
    for (country, iso2, iso3, income,
         gf, pepfar, gavi, gov, expected) in test_cases:

        inp = ClassifierInput(
            iso2=iso2, iso3=iso3, country_name=country,
            income_level=income, active_gf_grant=gf,
            pepfar_active=pepfar, gavi_eligible=gavi,
            governance_model=gov,
        )
        result = classify(inp)
        ok = result.category_code == expected
        if ok:
            passed += 1
        icon = "✓" if ok else "✗"
        print(
            f"{icon} {country:<15} [{result.category_code}] {result.category_label:<45} "
            f"confidence={result.confidence}"
        )
        if not ok:
            print(f"  EXPECTED {expected}, GOT {result.category_code}")
            print(f"  Reasoning: {result.reasoning}")

    print(f"\nResult: {passed}/{len(test_cases)} correct")

    # Spot-check priming
    print("\n=== PRIMING SPOT-CHECKS ===")
    zambia = classify(ClassifierInput(
        iso2="ZM", iso3="ZMB", country_name="Zambia",
        income_level="lower-middle",
        active_gf_grant=True, gavi_eligible=True,
    ))
    assert zambia.b2_priming.get("expect_dhis2") is True, "Zambia: expect_dhis2 missing"
    assert zambia.b2_priming.get("expect_openlmis") is True, "Zambia: expect_openlmis missing"
    print("✓ Zambia priming: expect_dhis2=True, expect_openlmis=True")

    switzerland = classify(ClassifierInput(
        iso2="CH", iso3="CHE", country_name="Switzerland",
        income_level="high",
    ))
    assert switzerland.localization_feasibility_flag is True
    assert switzerland.b2_priming.get("adoption_gap_likely") is True
    print("✓ Switzerland priming: feasibility_flag=True, adoption_gap_likely=True")

    print("\nALL ASSERTIONS PASSED")


if __name__ == "__main__":
    if "--test" in sys.argv or len(sys.argv) == 1:
        _run_tests()
    else:
        # Simple single-country CLI
        # Usage: python classifier.py ZM ZMB Zambia lower-middle --gf
        import argparse
        parser = argparse.ArgumentParser(description="Classify a country for DAK intelligence.")
        parser.add_argument("iso2");  parser.add_argument("iso3")
        parser.add_argument("name");  parser.add_argument("income")
        parser.add_argument("--gf",    action="store_true")
        parser.add_argument("--pepfar",action="store_true")
        parser.add_argument("--gavi",  action="store_true")
        parser.add_argument("--gov",   default=None)
        args = parser.parse_args()

        inp = ClassifierInput(
            iso2=args.iso2, iso3=args.iso3, country_name=args.name,
            income_level=args.income, active_gf_grant=args.gf,
            pepfar_active=args.pepfar, gavi_eligible=args.gavi,
            governance_model=args.gov,
        )
        out = classify(inp)
        print(f"Category    : [{out.category_code}] {out.category_label}")
        print(f"Profile     : {out.operational_profile}")
        print(f"Confidence  : {out.confidence}")
        print(f"Feasibility : {out.localization_feasibility_flag}")
        print(f"Reasoning   : {out.reasoning}")
        print(f"B2 priming  : {out.b2_priming}")
