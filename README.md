# WHO DAK Country Profile Skill

**Epidemiological and digital intelligence for WHO DAK localization.**

Generates a structured country profile for WHO experts preparing to localize a [Digital Adaptation Kit (DAK)](https://www.who.int/teams/digital-health-and-innovation/smart-guidelines) to a specific country and health domain.

---

## What it does

Given a **country** and a **DAK domain** (ANC, HIV, TB, Immunization), the skill:

1. Classifies the country into one of five digital health system profiles
2. Fetches verified epidemiological indicators (Block 1)
3. Maps the digital health landscape — what EHR is in use, who maintains it, whether it connects to the national HMIS, and what the real adoption rate is (Block 2)
4. Evaluates 14 operational risk flags and generates mandatory MoH questions
5. Produces two outputs: a human-readable HTML profile with clickable sources, and a compact JSON (~55 tokens) for agent pipelines

---

## Architecture

```
config/             Six YAML files — all classification logic, risk rules, and
                    source hierarchies live here. WHO staff edit these without
                    touching any Python.

intelligence/       Five Python modules — deterministic before any LLM call.
                    classifier.py → domain_router.py → evidence_classifier.py
                    → priming_engine.py → risk_assessor.py

retrieval/          HTTP client, PDF handler, manifest loader, document ingester.
                    Degrades gracefully on failure. Never installs silently.

sources/            Source catalogs, retrieval strategies, query templates,
                    baseline indicators, and domain metadata.

scoring/            Reliability formula (weighted, deterministic) and
                    Level 1 assertions (output not presented if any fails).

outputs/            HTML renderer (clickable source chips) and compact JSON writer.

evals/              LLM-as-judge rubric (12 dimensions) and golden test cases
                    for Zambia, Costa Rica, and Yemen (adversarial).
```

---

## Requirements

- Python ≥ 3.10
- `pyyaml >= 6.0` (required)
- `pypdf >= 6.0` (optional — enables PDF parsing)

```bash
pip install pyyaml
pip install pypdf  # optional
```

---

## Setup

```bash
git clone https://github.com/<your-org>/who-dak-intelligence
cd who-dak-intelligence
python retrieval/preflight.py --require-network
```

Preflight checks Python version, network access to WHO GHO and World Bank APIs, config files, intelligence modules, and output directory. Fix any errors before running the skill.

---

## Usage — Claude Project

1. **Project Instructions** — paste the contents of `SKILL.md`
2. **Project Knowledge** — upload all six files from `config/`
3. **Type** — `France + ANC` or `Zambia + Immunization`

The skill classifies the country, fetches indicators, runs cross-checks, evaluates risk flags, and produces HTML + compact JSON in `run_output/{country}_{domain}_{date}/`.

---

## Usage — Python

```python
import sys
sys.path.insert(0, 'intelligence')
sys.path.insert(0, 'retrieval')

from classifier import classify, ClassifierInput
from domain_router import route

# Classify country
inp = ClassifierInput(
    iso2="ZM", iso3="ZMB", country_name="Zambia",
    income_level="lower-middle",
    active_gf_grant=True, gavi_eligible=True,
)
result = classify(inp)
print(result.category_code)      # TS
print(result.operational_profile) # PROFILE_DONOR_GLOBAL_GOODS

# Get indicator set for domain
indicators = route("ANC", iso3="ZMB", iso2="ZM")
print(indicators.total_indicators)  # 16
```

---

## Running evaluations

```bash
# Judge an output against the Zambia golden case
# Load evals/rubrics/judge_prompt.md as the system prompt
# Pass the profile output + evals/golden/zambia_anc.json as context
# Any LLM with the judge prompt can score the output across 12 dimensions
```

---

## Country classification

| Code | Category | Example countries |
|------|----------|-------------------|
| TS | Target Standard | Zambia, Ethiopia, Ghana, Rwanda |
| CE | Centralized | Costa Rica, Uruguay, Thailand |
| FR | Fragmented | Italy, Germany, Spain, France |
| SV | Sovereign | China, India (national), Russia |
| HQ | HQ Paradox | Switzerland, Denmark, Kenya |
| MX | Mixed | Brazil (national vs state) |

Classification is deterministic — same input signals produce the same category. All logic is in `config/country_taxonomy.yml`.

---

## Confidence flags

| Code | Meaning | Source type |
|------|---------|-------------|
| V | Verified | WHO/UN Tier 1, ≤ 2 years |
| VA | Verified academic | Q1 peer-reviewed, ≤ 3 years |
| I | Inferred | Government portal or derived |
| IW | Inferred-weak | Stale or grey literature |
| U | Unknown | Attempted — not found |
| C | CONTRADICTED | Two Tier 1/2 sources disagree |

CONTRADICTED fields are never resolved — both values and sources are reported.

---

## Key design decisions

**Config-driven intelligence.** All classification criteria, risk flag rules, source hierarchies, and donor patterns are in YAML files. Adding a new country pattern or risk flag requires only a YAML edit — no code changes.

**Official silence rule.** Government portals suppress adoption failures and integration gaps. After every national government source, two mandatory PubMed queries run to surface what official sources omit. This rule is enforced in `config/evidence_rules.yml`.

**B2 gate.** Block 2 (digital landscape) does not execute if Block 1 reliability score < 0.50. Fragile states and data-sparse countries produce a skeleton profile and gap map instead of potentially fabricated digital landscape data.

**MCP-ready.** `retrieval/document_ingester.py` contains a stub (`_ingest_mcp_stub`) for the WHO smart-mcp-server connection. When the server is available, activate it in that function.

---

## Versioning

Config files are independently versioned (schema_version in each YAML). Bump:
- **major** for structural redesign
- **minor** for new dimensions, flags, or sources
- **patch** for corrections or wording updates

All empirical findings in config files include a date and source reference.

---

## License

Apache 2.0 — see [LICENSE](LICENSE)

---

## References

- Were / Muliokela et al. (2025). *JMIR Medical Informatics*. doi:10.2196/58858
- Muliokela et al. (2022). *Digital Health*. PMC8814973
- Lee & Singini (2023). *BMC Health Services Research*. PMC10566315
- Mehl, Ratanaprayul et al. (2021). *Lancet Digital Health*. WHO SMART Guidelines framework.
