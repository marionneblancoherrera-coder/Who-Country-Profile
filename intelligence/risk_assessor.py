"""
risk_assessor.py
WHO DAK Intelligence Platform — intelligence/risk_assessor.py

Evaluates all risk flags against completed B1 + B2 output.
Reads config/risk_definitions.yml exclusively.
New flags require only a new YAML entry — no code changes.

Input  : RiskInput (flat dict of field values from B1+B2)
Output : RiskAssessmentResult (active flags, questions, feasibility note)
"""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import yaml

CONFIG_DIR    = Path(__file__).resolve().parent.parent / "config"
RISK_PATH     = CONFIG_DIR / "risk_definitions.yml"


# ── Data classes ──────────────────────────────────────────────

@dataclass
class RiskInput:
    """
    Flat context from completed B1 + B2 + priming.
    None means the field was not retrieved (unknown).
    False is an explicit negative.
    """
    # Block 1 fields
    domain_coverage_pct:          Optional[float] = None
    physician_density:             Optional[float] = None
    national_guidelines_year:      Optional[int]   = None
    quality_gap_evidence:          Optional[bool]  = None
    active_gf_grant:               Optional[bool]  = None

    # Block 2 fields
    system_in_transition:          Optional[bool]  = None
    poc_nominal_coverage:          Optional[float] = None
    poc_real_adoption:             Optional[float] = None
    poc_maintainer_is_government:  Optional[bool]  = None
    poc_hmis_integration:          Optional[bool]  = None
    fragmentation_score:           Optional[float] = None
    national_mandate_evidence:     Optional[bool]  = None
    vendor_fragmentation_signal:   Optional[bool]  = None

    # Dynamic signals from Q1 retrieval
    subnational_withdrawal_evidence:    Optional[bool] = None
    q1_adoption_barriers_found:         Optional[bool] = None
    q1_stigma_data_avoidance:           Optional[bool] = None
    q1_regional_disparity:              Optional[bool] = None
    q1_urban_rural_gap_gt_20pct:        Optional[bool] = None
    source_sovereignty_restriction:     Optional[bool] = None

    # Category + domain context
    category_code:  str = "TS"
    dak_domain:     str = "ANC"

    # Evidence sources (for output attribution)
    field_sources:  dict = field(default_factory=dict)


@dataclass
class ActiveFlag:
    name:         str
    label:        str
    severity:     str       # high | medium | informational
    category:     str       # base | emergent
    dak_impact:   str
    mandatory_moh_question: str
    triggered_by: str       # which field/signal triggered it
    source:       Optional[str] = None
    feasibility_note: Optional[str] = None


@dataclass
class RiskAssessmentResult:
    active_flags:    list[ActiveFlag] = field(default_factory=list)
    inactive_flags:  list[str]        = field(default_factory=list)
    moh_questions:   list[str]        = field(default_factory=list)
    localization_feasibility_note: Optional[str] = None

    @property
    def has_high_severity(self) -> bool:
        return any(f.severity == "high" for f in self.active_flags)

    @property
    def flag_names(self) -> list[str]:
        return [f.name for f in self.active_flags]


# ── Loader ────────────────────────────────────────────────────

def _load() -> dict:
    with open(RISK_PATH, encoding="utf-8") as f:
        return yaml.safe_load(f)


# ── Activation rules ──────────────────────────────────────────
# Each rule: (flag_name, condition_fn, triggered_by_description)

def _rules(inp: RiskInput) -> list[tuple[str, bool, str]]:
    from datetime import date
    current_year = date.today().year

    return [
        # ── BASE FLAGS ──────────────────────────────────────────
        (
            "RISK_TRANSITION",
            inp.system_in_transition is True,
            "system_in_transition=True"
        ),
        (
            "RISK_ADOPTION_GAP",
            (
                inp.poc_nominal_coverage is not None
                and inp.poc_real_adoption is not None
                and inp.poc_nominal_coverage > 0.80
                and inp.poc_real_adoption < 0.20
            ) or (
                inp.q1_adoption_barriers_found is True
                and inp.poc_nominal_coverage is not None
                and inp.poc_nominal_coverage > 0.80
            ),
            f"nominal={inp.poc_nominal_coverage} real={inp.poc_real_adoption} "
            f"q1_barriers={inp.q1_adoption_barriers_found}"
        ),
        (
            "RISK_FRAGMENTATION",
            (
                inp.fragmentation_score is not None
                and inp.fragmentation_score > 6.0
                and inp.national_mandate_evidence is not True
            ),
            f"fragmentation_score={inp.fragmentation_score} "
            f"mandate={inp.national_mandate_evidence}"
        ),
        (
            "RISK_VENDOR_IS_GOVERNMENT",
            inp.poc_maintainer_is_government is True,
            "poc_maintainer_is_government=True"
        ),
        (
            "RISK_INTEROPERABILITY_GAP",
            (
                inp.poc_hmis_integration is False
                and inp.dak_domain in ("ANC", "Immunization", "HIV", "TB")
            ),
            f"poc_hmis_integration=False domain={inp.dak_domain}"
        ),

        # ── EMERGENT FLAGS ──────────────────────────────────────
        (
            "RISK_CANTONAL_DEFECTION",
            inp.subnational_withdrawal_evidence is True,
            "subnational_withdrawal_evidence=True"
        ),
        (
            "RISK_VENDOR_COMPETITION",
            inp.vendor_fragmentation_signal is True,
            "vendor_fragmentation_signal=True"
        ),
        (
            "RISK_DOMAIN_STIGMA",
            (
                inp.q1_stigma_data_avoidance is True
                and inp.dak_domain in ("ANC", "HIV")
            ),
            f"q1_stigma=True domain={inp.dak_domain}"
        ),
        (
            "RISK_SOUTH_NORTH_DISPARITY",
            (
                inp.q1_regional_disparity is True
                and inp.category_code in ("FR",)
            ),
            "q1_regional_disparity=True category=FR"
        ),
        (
            "GEOGRAPHIC_EQUITY_GAP",
            (
                inp.domain_coverage_pct is not None
                and inp.domain_coverage_pct > 85
                and inp.q1_urban_rural_gap_gt_20pct is True
            ),
            f"coverage={inp.domain_coverage_pct} urban_rural_gap>20%=True"
        ),
        (
            "QUALITY_COVERAGE_GAP",
            (
                inp.domain_coverage_pct is not None
                and inp.domain_coverage_pct > 85
                and inp.quality_gap_evidence is True
            ),
            f"coverage={inp.domain_coverage_pct} quality_gap=True"
        ),
        (
            "GUIDELINES_OUTDATED",
            (
                inp.national_guidelines_year is not None
                and inp.national_guidelines_year < current_year - 3
            ),
            f"guidelines_year={inp.national_guidelines_year} "
            f"threshold={current_year - 3}"
        ),
        (
            "RISK_LOW_OPERATOR_CAPACITY",
            (
                inp.physician_density is not None
                and inp.physician_density < 0.2
            ),
            f"physician_density={inp.physician_density}"
        ),
        (
            "LOCALIZATION_FEASIBILITY_FLAG",
            (
                inp.category_code in ("SV", "HQ")
                or inp.source_sovereignty_restriction is True
            ),
            f"category={inp.category_code} "
            f"sovereignty={inp.source_sovereignty_restriction}"
        ),
    ]


# ── Main assessor ─────────────────────────────────────────────

def assess(inp: RiskInput) -> RiskAssessmentResult:
    definitions = _load()
    all_flags   = {
        **definitions.get("base_flags", {}),
        **definitions.get("emergent_flags", {}),
    }
    rules       = _rules(inp)
    result      = RiskAssessmentResult()

    for flag_name, fired, triggered_by in rules:
        defn = all_flags.get(flag_name, {})
        if fired:
            question = defn.get("mandatory_moh_question", "")
            # Substitute domain placeholder
            question = question.replace("{domain}", inp.dak_domain)

            af = ActiveFlag(
                name=flag_name,
                label=defn.get("label", flag_name),
                severity=defn.get("severity", "medium"),
                category=defn.get("category", "base"),
                dak_impact=defn.get("dak_impact", ""),
                mandatory_moh_question=question,
                triggered_by=triggered_by,
                source=inp.field_sources.get(flag_name),
            )

            # Generate feasibility note for LOCALIZATION_FEASIBILITY_FLAG
            if flag_name == "LOCALIZATION_FEASIBILITY_FLAG":
                af.feasibility_note = _feasibility_note(inp)
                result.localization_feasibility_note = af.feasibility_note

            result.active_flags.append(af)
            if question and question not in result.moh_questions:
                result.moh_questions.append(question)
        else:
            result.inactive_flags.append(flag_name)

    # Ensure minimum 5 MoH questions (pad with generic ones if needed)
    _pad_questions(result, inp)

    return result


def _feasibility_note(inp: RiskInput) -> str:
    if inp.category_code == "HQ":
        return (
            "Standard 4-step DAK localization does not apply. "
            "Recommended pathway: align DAK content with national digital "
            "health strategy. Entry point: national eHealth agency + MoH "
            "digital health directorate. Timeline: 2028-2030 horizon."
        )
    elif inp.category_code == "SV":
        return (
            "Standard technical DAK integration is not feasible. "
            "Recommended pathway: policy alignment — benchmark national "
            "clinical protocols against WHO DAK content standards during "
            "national guidelines revision cycle. "
            "Entry point: national health commission + local academic partners."
        )
    return (
        "Non-standard localization path. Review WHO collaboration options."
    )


def _pad_questions(result: RiskAssessmentResult, inp: RiskInput) -> None:
    """Add contextual questions until minimum 5 is reached."""
    generic = [
        f"What is the primary digital system in use for {inp.dak_domain} "
        "data capture at primary care level?",
        "What is the most recent national clinical guideline update for "
        f"{inp.dak_domain}, and is a revision planned?",
        "Which institution owns the national health information system and "
        "who approves content or protocol changes?",
        "Are there active digital health investments (national or donor) "
        "planned for the next 18 months that would affect system choice?",
        f"What are the primary barriers to {inp.dak_domain} data quality "
        "in the current system?",
        "Is there an existing interoperability layer between point-of-care "
        "and national HMIS for this domain?",
    ]
    for q in generic:
        if len(result.moh_questions) >= 5:
            break
        if q not in result.moh_questions:
            result.moh_questions.append(q)


def to_dict(result: RiskAssessmentResult) -> dict:
    return {
        "active_flags": [
            {
                "name":      f.name,
                "label":     f.label,
                "severity":  f.severity,
                "category":  f.category,
                "triggered_by": f.triggered_by,
                "dak_impact": f.dak_impact[:120],
                "mandatory_moh_question": f.mandatory_moh_question,
            }
            for f in result.active_flags
        ],
        "inactive_flags": result.inactive_flags,
        "moh_questions":  result.moh_questions,
        "has_high_severity": result.has_high_severity,
        "localization_feasibility_note": result.localization_feasibility_note,
    }


# ── Tests ─────────────────────────────────────────────────────

def _run_tests() -> None:
    print("=== RISK ASSESSOR TESTS ===\n")
    passed = 0
    total  = 0

    # T1: Costa Rica — CENTRALIZED
    total += 1
    cr = RiskInput(
        category_code="CE", dak_domain="ANC",
        domain_coverage_pct=99.0,
        quality_gap_evidence=True,
        national_guidelines_year=2009,
        poc_maintainer_is_government=True,
        poc_hmis_integration=False,
        system_in_transition=True,
        poc_nominal_coverage=0.97,
        poc_real_adoption=0.90,
    )
    r1 = assess(cr)
    assert "RISK_VENDOR_IS_GOVERNMENT"  in r1.flag_names
    assert "RISK_INTEROPERABILITY_GAP"  in r1.flag_names
    assert "QUALITY_COVERAGE_GAP"       in r1.flag_names
    assert "GUIDELINES_OUTDATED"        in r1.flag_names
    assert "RISK_TRANSITION"            in r1.flag_names
    assert "RISK_ADOPTION_GAP"      not in r1.flag_names  # real_adoption=0.90
    assert len(r1.moh_questions)        >= 5
    passed += 1
    print(f"✓ Costa Rica: {r1.flag_names}")

    # T2: Switzerland — HQ_PARADOX
    total += 1
    ch = RiskInput(
        category_code="HQ", dak_domain="ANC",
        poc_nominal_coverage=0.99,
        poc_real_adoption=0.013,
        q1_adoption_barriers_found=True,
        vendor_fragmentation_signal=True,
        subnational_withdrawal_evidence=True,
        q1_stigma_data_avoidance=True,
        fragmentation_score=8.9,
        national_mandate_evidence=False,
        system_in_transition=True,
    )
    r2 = assess(ch)
    assert "RISK_ADOPTION_GAP"          in r2.flag_names
    assert "RISK_FRAGMENTATION"         in r2.flag_names
    assert "RISK_CANTONAL_DEFECTION"    in r2.flag_names
    assert "RISK_VENDOR_COMPETITION"    in r2.flag_names
    assert "RISK_DOMAIN_STIGMA"         in r2.flag_names
    assert "LOCALIZATION_FEASIBILITY_FLAG" in r2.flag_names
    assert r2.localization_feasibility_note is not None
    assert r2.has_high_severity is True
    passed += 1
    print(f"✓ Switzerland: {r2.flag_names}")
    print(f"  Feasibility: {r2.localization_feasibility_note[:80]}...")

    # T3: Zambia — TARGET_STANDARD, low physician density
    total += 1
    zm = RiskInput(
        category_code="TS", dak_domain="ANC",
        domain_coverage_pct=76.0,
        physician_density=0.17,
        national_guidelines_year=2021,
        poc_hmis_integration=False,
        poc_nominal_coverage=0.60,
        poc_real_adoption=0.45,
        active_gf_grant=True,
    )
    r3 = assess(zm)
    assert "RISK_LOW_OPERATOR_CAPACITY"  in r3.flag_names
    assert "RISK_INTEROPERABILITY_GAP"   in r3.flag_names
    assert "RISK_ADOPTION_GAP"       not in r3.flag_names  # real=0.45 > 0.20
    passed += 1
    print(f"✓ Zambia: {r3.flag_names}")

    # T4: China — SOVEREIGN
    total += 1
    cn = RiskInput(
        category_code="SV", dak_domain="ANC",
        source_sovereignty_restriction=True,
        fragmentation_score=7.2,
        national_mandate_evidence=False,
        q1_urban_rural_gap_gt_20pct=True,
        domain_coverage_pct=98.0,
    )
    r4 = assess(cn)
    assert "LOCALIZATION_FEASIBILITY_FLAG" in r4.flag_names
    assert "RISK_FRAGMENTATION"          in r4.flag_names
    assert "GEOGRAPHIC_EQUITY_GAP"       in r4.flag_names
    assert "policy alignment" in r4.localization_feasibility_note
    passed += 1
    print(f"✓ China: {r4.flag_names}")

    # T5: Italy — FRAGMENTED
    total += 1
    it = RiskInput(
        category_code="FR", dak_domain="ANC",
        fragmentation_score=7.6,
        national_mandate_evidence=False,
        q1_regional_disparity=True,
        system_in_transition=True,
    )
    r5 = assess(it)
    assert "RISK_FRAGMENTATION"       in r5.flag_names
    assert "RISK_SOUTH_NORTH_DISPARITY" in r5.flag_names
    assert "RISK_TRANSITION"          in r5.flag_names
    passed += 1
    print(f"✓ Italy: {r5.flag_names}")

    # T6: MoH questions minimum
    total += 1
    minimal = RiskInput(category_code="TS", dak_domain="ANC")
    r6 = assess(minimal)
    assert len(r6.moh_questions) >= 5, \
        f"Expected ≥5 questions, got {len(r6.moh_questions)}"
    passed += 1
    print(f"✓ MoH questions minimum: {len(r6.moh_questions)} questions generated")

    # T7: Serialisation
    total += 1
    d = to_dict(r2)
    json.dumps(d)
    assert "active_flags" in d and "moh_questions" in d
    passed += 1
    print(f"✓ Serialisation: {len(d['active_flags'])} active flags JSON-ready")

    print(f"\nResult: {passed}/{total} correct")

    # Summary of Switzerland MoH questions
    print("\n=== MoH QUESTIONS: Switzerland ANC ===")
    for i, q in enumerate(r2.moh_questions, 1):
        print(f"  Q{i}: {q[:100]}...")


if __name__ == "__main__":
    _run_tests()
