"""
domain_router.py
WHO DAK Intelligence Platform — intelligence/domain_router.py

Routes DAK domain input to the correct indicator sets,
API endpoints, infrastructure focus, and B2 signals.
Reads config/domain_indicators.yml exclusively.

Input  : dak_domain (str), country_iso3 (str)
Output : DomainRouteResult (indicators, api_calls, infrastructure, b2_signals)
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import yaml

CONFIG_DIR      = Path(__file__).resolve().parent.parent / "config"
INDICATORS_PATH = CONFIG_DIR / "domain_indicators.yml"

SUPPORTED_DOMAINS = {"ANC", "HIV", "TB", "Immunization"}

API_BASE = {
    "world_bank": "https://api.worldbank.org/v2/country/{iso3}/indicator/{code}?format=json&per_page=100",
    "who_gho":    "https://ghoapi.azureedge.net/api/{code}",
    "unicef":     "https://data.unicef.org/country/{iso2}/",
}


# ── Data classes ──────────────────────────────────────────────

@dataclass
class IndicatorSpec:
    field_name:      str
    label:           str
    source_type:     str
    api:             Optional[str]
    api_url:         Optional[str]
    profile_section: str
    recency:         str
    b2_signal:       Optional[str] = None
    note:            Optional[str] = None
    conflict_note:   Optional[str] = None
    alt_source:      Optional[str] = None


@dataclass
class DomainRouteResult:
    dak_domain:          str
    iso3:                str
    iso2:                str
    universal_indicators: list[IndicatorSpec] = field(default_factory=list)
    domain_indicators:   list[IndicatorSpec] = field(default_factory=list)
    infrastructure_focus: dict = field(default_factory=dict)
    b2_routing_signals:  list[dict] = field(default_factory=list)
    who_ig:              str = ""
    total_indicators:    int = 0


# ── Loader ────────────────────────────────────────────────────

def _load() -> dict:
    if not INDICATORS_PATH.exists():
        raise FileNotFoundError(f"domain_indicators.yml not found at {INDICATORS_PATH}")
    with open(INDICATORS_PATH, encoding="utf-8") as f:
        return yaml.safe_load(f)


def _build_url(api: Optional[str], code: Optional[str],
               iso3: str, iso2: str) -> Optional[str]:
    if api == "world_bank" and code:
        return API_BASE["world_bank"].format(iso3=iso3, code=code)
    if api == "who_gho" and code:
        return API_BASE["who_gho"].format(code=code)
    if api == "unicef":
        return API_BASE["unicef"].format(iso2=iso2)
    return None


def _parse_indicators(
    raw: dict, iso3: str, iso2: str
) -> list[IndicatorSpec]:
    specs = []
    for field_name, v in raw.items():
        api = v.get("api")
        code = v.get("code")
        specs.append(IndicatorSpec(
            field_name=field_name,
            label=v.get("label", field_name),
            source_type=v.get("source", "global_normative"),
            api=api,
            api_url=_build_url(api, code, iso3, iso2),
            profile_section=v.get("profile_section", ""),
            recency=v.get("recency", "current"),
            b2_signal=v.get("b2_signal"),
            note=v.get("note"),
            conflict_note=v.get("conflict_note"),
            alt_source=v.get("alt_source"),
        ))
    return specs


# ── Router ────────────────────────────────────────────────────

def route(dak_domain: str, iso3: str, iso2: Optional[str] = None) -> DomainRouteResult:
    """
    Return the full indicator set and routing metadata for a
    DAK domain + country combination.
    """
    domain = dak_domain.strip()
    if domain not in SUPPORTED_DOMAINS:
        raise ValueError(
            f"Unsupported DAK domain: '{domain}'. "
            f"Supported: {sorted(SUPPORTED_DOMAINS)}"
        )

    iso2 = iso2 or iso3[:2].upper()
    data = _load()

    universal = _parse_indicators(
        data["universal_indicators"], iso3=iso3, iso2=iso2
    )

    domain_block = data["domain_indicator_sets"][domain]
    domain_inds  = _parse_indicators(
        domain_block["indicators"], iso3=iso3, iso2=iso2
    )
    infra        = domain_block.get("infrastructure_focus", {})
    who_ig       = domain_block.get("who_ig", "")

    # B2 routing signals relevant to this domain
    all_signals  = data.get("b2_routing_signals", {})
    relevant     = _filter_signals(all_signals, domain)

    result = DomainRouteResult(
        dak_domain=domain,
        iso3=iso3,
        iso2=iso2,
        universal_indicators=universal,
        domain_indicators=domain_inds,
        infrastructure_focus=infra,
        b2_routing_signals=relevant,
        who_ig=who_ig,
        total_indicators=len(universal) + len(domain_inds),
    )
    return result


def _filter_signals(signals: dict, domain: str) -> list[dict]:
    """Keep signals that apply to all domains or to this domain."""
    out = []
    for key, sig in signals.items():
        trigger = sig.get("trigger", "")
        # Domain-specific signal
        if "dak_domain" in trigger and domain not in trigger:
            continue
        out.append({"name": key, **sig})
    return out


# ── Summary helpers ───────────────────────────────────────────

def summarise(result: DomainRouteResult) -> str:
    lines = [
        f"Domain : {result.dak_domain}  |  Country: {result.iso3} ({result.iso2})",
        f"WHO IG : {result.who_ig}",
        f"Total indicators to fetch: {result.total_indicators}",
        "",
        "Universal indicators:",
    ]
    for ind in result.universal_indicators:
        url_short = (ind.api_url or "manual")[:60]
        lines.append(f"  {ind.field_name:<30} [{ind.source_type[:8]}] {url_short}")

    lines.append(f"\nDomain-specific ({result.dak_domain}):")
    for ind in result.domain_indicators:
        url_short = (ind.api_url or "manual")[:60]
        flag = " ← B2 signal" if ind.b2_signal else ""
        lines.append(f"  {ind.field_name:<30} [{ind.source_type[:8]}] {url_short}{flag}")

    lines.append(f"\nInfrastructure focus:")
    for k, v in result.infrastructure_focus.items():
        if isinstance(v, list):
            lines.append(f"  {k}: {v}")
        else:
            short = str(v)[:80] + "..." if len(str(v)) > 80 else str(v)
            lines.append(f"  {k}: {short}")

    lines.append(f"\nActive B2 routing signals: {len(result.b2_routing_signals)}")
    for sig in result.b2_routing_signals:
        lines.append(f"  {sig['name']}: trigger={sig.get('trigger','')[:50]}")

    return "\n".join(lines)


# ── Tests ─────────────────────────────────────────────────────

def _run_tests() -> None:
    print("=== DOMAIN ROUTER TESTS ===\n")
    passed = 0
    total  = 0

    for domain in ["ANC", "HIV", "TB", "Immunization"]:
        total += 1
        result = route(domain, iso3="ZMB", iso2="ZM")
        assert result.dak_domain == domain
        assert result.total_indicators > 0
        assert len(result.universal_indicators) == 9
        assert len(result.domain_indicators) > 0
        assert result.who_ig != ""
        assert "infrastructure_focus" in result.__dict__
        passed += 1
        print(
            f"✓ {domain:<15} "
            f"total={result.total_indicators} "
            f"(universal={len(result.universal_indicators)} "
            f"+ domain={len(result.domain_indicators)}) "
            f"signals={len(result.b2_routing_signals)}"
        )

    # ANC-specific checks
    total += 1
    anc = route("ANC", iso3="ZMB", iso2="ZM")
    anc_fields = [i.field_name for i in anc.domain_indicators]
    assert "maternal_mortality_ratio" in anc_fields, "Missing MMR"
    assert "anc4_coverage" in anc_fields, "Missing ANC4+"
    # Check conflict note exists on MMR
    mmr = next(i for i in anc.domain_indicators if i.field_name == "maternal_mortality_ratio")
    assert mmr.conflict_note is not None, "MMR conflict note missing"
    passed += 1
    print(f"✓ ANC MMR conflict_note present: '{mmr.conflict_note[:60]}...'")

    # URL generation checks
    total += 1
    wb_inds = [i for i in anc.universal_indicators if i.api == "world_bank"]
    assert all(i.api_url and "ZMB" in i.api_url for i in wb_inds), \
        "World Bank URL not generated correctly"
    gho_inds = [i for i in anc.domain_indicators if i.api == "who_gho"]
    gho_with_url = [i for i in gho_inds if i.api_url]
    assert all("ghoapi" in i.api_url for i in gho_with_url), "WHO GHO URL malformed"


    passed += 1
    print(f"✓ API URLs generated: WB={len(wb_inds)} GHO={len(gho_inds)}")

    # Domain-specific signal filtering
    total += 1
    hiv = route("HIV", iso3="ZMB", iso2="ZM")
    hiv_signal_names = [s["name"] for s in hiv.b2_routing_signals]
    assert "donor_pepfar_active" in hiv_signal_names, \
        "PEPFAR signal missing from HIV routing"
    passed += 1
    print(f"✓ HIV routing includes donor_pepfar_active signal")

    # Unsupported domain raises
    total += 1
    try:
        route("MALARIA", iso3="ZMB")
        assert False, "Should have raised ValueError"
    except ValueError:
        passed += 1
        print(f"✓ Unsupported domain raises ValueError correctly")

    # Immunization GHO codes
    total += 1
    imm = route("Immunization", iso3="ETH", iso2="ET")
    imm_gho = [i for i in imm.domain_indicators if i.api == "who_gho"]
    assert len(imm_gho) >= 3, "Expected ≥3 GHO immunization indicators"
    dtp3 = next((i for i in imm_gho if "WHS4_100" in (i.api_url or "")), None)
    assert dtp3 is not None, "DTP3 GHO URL missing"
    passed += 1
    print(f"✓ Immunization: {len(imm_gho)} GHO indicators, DTP3 URL confirmed")

    print(f"\nResult: {passed}/{total} correct")

    # Print ANC summary as integration sample
    print("\n=== ANC ROUTE SUMMARY (Zambia) ===")
    print(summarise(route("ANC", iso3="ZMB", iso2="ZM")))


if __name__ == "__main__":
    if "--test" in sys.argv or len(sys.argv) == 1:
        _run_tests()
    else:
        import argparse
        parser = argparse.ArgumentParser()
        parser.add_argument("domain")
        parser.add_argument("iso3")
        parser.add_argument("--iso2", default=None)
        args = parser.parse_args()
        print(summarise(route(args.domain, args.iso3, args.iso2)))
