"""
reliability_formula.py
WHO DAK Intelligence Platform — scoring/reliability_formula.py
Deterministic reliability score. Same input → same score always.
"""
from __future__ import annotations
from dataclasses import dataclass
from typing import Optional

B2_GATE   = 0.50
PENALTIES = {"FRAGILE_STATE_ESTIMATE": -0.15, "SURVEY_AGE_WARNING": -0.08}

@dataclass
class BlockScore:
    completeness: float; source_quality: float
    recency: float;      q1_consensus: float
    silence_coverage: float; raw: float
    penalties: list[str]; penalty_total: float
    final: float; label: str

@dataclass
class ProfileScore:
    b1: BlockScore; b2: Optional[BlockScore]
    combined: float; label: str; note: str

def score_block(
    total_fields: int, filled: int, tier1_2: int,
    recent: int, no_conflict: int, q1_run: bool,
    active_flags: list[str]
) -> BlockScore:
    if filled == 0:
        return BlockScore(0,0,0,0,0,0,[],0,0,"INSUFFICIENT")
    w = dict(completeness=0.25, source_quality=0.30, recency=0.25, q1_consensus=0.20)
    completeness    = filled  / total_fields
    source_quality  = tier1_2 / filled
    recency         = recent  / filled
    q1_consensus    = no_conflict / filled
    silence         = 1.0 if q1_run else 0.0
    raw = (completeness  * w["completeness"]  +
           source_quality* w["source_quality"] +
           recency       * w["recency"]        +
           q1_consensus  * w["q1_consensus"]
    ) * 0.90 + silence * 0.10
    pens = [f for f in active_flags if f in PENALTIES]
    pen_total = sum(PENALTIES[p] for p in pens)
    if not q1_run:
        pens.append("Q1_NOT_RUN"); pen_total += -0.10
    final = round(max(0.0, raw + pen_total), 3)
    return BlockScore(
        completeness=round(completeness,3), source_quality=round(source_quality,3),
        recency=round(recency,3), q1_consensus=round(q1_consensus,3),
        silence_coverage=silence, raw=round(raw,3),
        penalties=pens, penalty_total=round(pen_total,3),
        final=final, label=_label(final)
    )

def score_profile(b1: BlockScore, b2: Optional[BlockScore]) -> ProfileScore:
    if b2 is None:
        c = round(b1.final * 0.6, 3)
        return ProfileScore(b1, None, c, _label(c), "B2 not executed.")
    c = round((b1.final + b2.final) / 2, 3)
    notes = {
        "HIGH CONFIDENCE":   "Ready for pre-mission use.",
        "MEDIUM CONFIDENCE": "Usable — verify inferred-weak fields before MoH meeting.",
        "LOW CONFIDENCE":    "Map of questions, not briefing document.",
        "INSUFFICIENT":      "Do not use — escalate to manual research.",
    }
    label = _label(c)
    return ProfileScore(b1, b2, c, label, notes.get(label, ""))

def b2_gate_passed(b1: BlockScore) -> bool:
    return b1.final >= B2_GATE

def _label(s: float) -> str:
    if s >= 0.80: return "HIGH CONFIDENCE"
    if s >= 0.60: return "MEDIUM CONFIDENCE"
    if s >= 0.40: return "LOW CONFIDENCE"
    return "INSUFFICIENT"

def format_report(p: ProfileScore) -> str:
    b1, b2 = p.b1, p.b2
    lines = [
        f"Reliability: {p.combined} — {p.label}",
        f"  B1: {b1.final}  (completeness={b1.completeness:.0%}  quality={b1.source_quality:.0%}  recency={b1.recency:.0%})",
    ]
    if b1.penalties: lines.append(f"  B1 penalties: {b1.penalties}")
    if b2:
        lines.append(f"  B2: {b2.final}  (completeness={b2.completeness:.0%}  quality={b2.source_quality:.0%}  recency={b2.recency:.0%})")
        if b2.penalties: lines.append(f"  B2 penalties: {b2.penalties}")
    lines.append(f"  Note: {p.note}")
    return "\n".join(lines)

if __name__ == "__main__":
    # Costa Rica expected 0.77
    b1 = score_block(14, 13, 9, 10, 12, True, ["GUIDELINES_OUTDATED"])
    b2 = score_block(12, 10, 7,  8, 10, True, [])
    p  = score_profile(b1, b2)
    print(format_report(p))
    assert 0.70 <= p.combined <= 0.85, f"Score {p.combined} out of expected range"
    print("✓ reliability_formula OK")
