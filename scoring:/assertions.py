"""
assertions.py
WHO DAK Intelligence Platform — scoring/assertions.py
Level 1 automated checks. Output not presented if any fails.
"""
from __future__ import annotations
from dataclasses import dataclass, field

VALID_CONFIDENCE = {"V","VA","I","IW","U","C"}
VALID_CATEGORIES = {"HQ","SV","FR","CE","TS","MX"}
BASE_FLAGS = {
    "RISK_TRANSITION","RISK_ADOPTION_GAP","RISK_FRAGMENTATION",
    "RISK_VENDOR_IS_GOVERNMENT","RISK_INTEROPERABILITY_GAP",
}
MIN_MOH_QUESTIONS = 5


@dataclass
class AssertionResult:
    name:    str
    passed:  bool
    message: str


@dataclass
class AssertionReport:
    results: list[AssertionResult] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return all(r.passed for r in self.results)

    @property
    def failures(self) -> list[AssertionResult]:
        return [r for r in self.results if not r.passed]

    def print(self) -> None:
        for r in self.results:
            print(f"  {'✓' if r.passed else '✗'} {r.name}: {r.message}")
        print()
        if self.passed:
            print("  Level 1 assertions passed.")
        else:
            print(f"  {len(self.failures)} failure(s) — output must not be presented.")


def run(output: dict) -> AssertionReport:
    report = AssertionReport()
    A = report.results.append

    # A1: country_category valid
    cat = output.get("country_category","")
    A(AssertionResult("A1_category",
        cat in VALID_CATEGORIES,
        f"'{cat}'" if cat in VALID_CATEGORIES else f"invalid: '{cat}'"))

    # A2: reliability_score in [0,1]
    score = output.get("reliability_score")
    ok = isinstance(score,(int,float)) and 0.0 <= score <= 1.0
    A(AssertionResult("A2_score", ok,
        f"{score:.3f}" if ok else f"invalid: {score!r}"))

    # A3: block1 non-empty
    b1 = output.get("block1",{})
    A(AssertionResult("A3_block1",
        isinstance(b1,dict) and len(b1) > 0,
        f"{len(b1)} fields" if b1 else "missing or empty"))

    # A4: all confidence codes valid
    all_fields = {**b1, **(output.get("block2") or {})}
    bad = [f for f,v in all_fields.items()
           if isinstance(v,dict) and v.get("confidence_code") not in VALID_CONFIDENCE]
    A(AssertionResult("A4_confidence_codes",
        not bad, "OK" if not bad else f"invalid in: {bad[:3]}"))

    # A5: non-unknown fields have source_url
    no_url = [f for f,v in all_fields.items()
              if isinstance(v,dict)
              and v.get("confidence_code") not in ("U",None)
              and not v.get("source_url")]
    A(AssertionResult("A5_source_urls",
        not no_url, "OK" if not no_url else f"missing: {no_url[:3]}"))

    # A6: all 5 base flags evaluated
    evaluated  = set(output.get("risk_flags_evaluated",[]))
    missing_fl = BASE_FLAGS - evaluated
    A(AssertionResult("A6_base_flags",
        not missing_fl, "OK" if not missing_fl else f"not evaluated: {missing_fl}"))

    # A7: minimum 5 MoH questions
    qs = output.get("moh_questions",[])
    A(AssertionResult("A7_moh_questions",
        len(qs) >= MIN_MOH_QUESTIONS,
        f"{len(qs)} questions" if len(qs) >= MIN_MOH_QUESTIONS
        else f"only {len(qs)}, minimum {MIN_MOH_QUESTIONS}"))

    # A8: dak_target_system deferred when system_in_transition
    b2         = output.get("block2") or {}
    target     = _val(b2,"dak_target_system")
    transition = _val(b2,"system_in_transition")
    bad_target = (transition is True and target
                  and "pending" not in str(target).lower()
                  and "transition" not in str(target).lower())
    A(AssertionResult("A8_target_consistency",
        not bad_target,
        "OK" if not bad_target
        else "transition=True but target makes direct recommendation"))

    # A9: no None value on non-unknown fields
    null_fields = [f for f,v in all_fields.items()
                   if isinstance(v,dict)
                   and v.get("value") is None
                   and v.get("confidence_code") not in ("U",None)]
    A(AssertionResult("A9_no_null_values",
        not null_fields, "OK" if not null_fields else f"null in: {null_fields[:3]}"))

    # A10: block2 only when b1_score >= 0.50
    b2_present = output.get("block2") is not None
    b1_score   = output.get("b1_score", score)
    gate_fail  = (b2_present
                  and isinstance(b1_score,(int,float))
                  and b1_score < 0.50)
    A(AssertionResult("A10_b2_gate",
        not gate_fail,
        "OK" if not gate_fail
        else f"b2 present but b1_score={b1_score:.2f} < 0.50"))

    return report


def _val(block: dict, field_name: str):
    fld = block.get(field_name)
    return fld.get("value") if isinstance(fld,dict) else fld


if __name__ == "__main__":
    GOOD = {
        "country_category": "CE",
        "reliability_score": 0.77,
        "b1_score": 0.77,
        "risk_flags_evaluated": list(BASE_FLAGS),
        "moh_questions": ["Q1","Q2","Q3","Q4","Q5"],
        "block1": {
            "anc4": {"value":99,"confidence_code":"V",
                     "source_url":"https://data.unicef.org/country/cr/"},
        },
        "block2": {
            "poc_system_name":    {"value":"EDUS","confidence_code":"V",
                                   "source_url":"https://publications.iadb.org"},
            "system_in_transition":{"value":False,"confidence_code":"V",
                                    "source_url":"https://ccss.sa.cr"},
            "dak_target_system":  {"value":"EDUS — requires CCSS agreement",
                                   "confidence_code":"I","source_url":None},
        },
    }
    print("=== GOOD CASE (A5 expected: dak_target_system has no url) ===")
    run(GOOD).print()

    BAD = {
        "country_category": "INVALID",
        "reliability_score": 1.5,
        "b1_score": 0.30,
        "risk_flags_evaluated": ["RISK_TRANSITION"],
        "moh_questions": ["Q1"],
        "block1": {},
        "block2": {"poc":{"value":"X","confidence_code":"V","source_url":None}},
    }
    print("=== BAD CASE ===")
    r2 = run(BAD)
    r2.print()
    assert len(r2.failures) >= 5
    print(f"✓ Caught {len(r2.failures)} failures as expected")
