# Changelog

## v2.0.0 — 2026-05-25

### Added
- Multi-dimensional country taxonomy (6 structural dimensions + fragmentation index)
- Five derived operational profiles replacing narrative category labels
- `source_catalog.yml`, `retrieval_strategy.yml`, `query_templates.yml` — 3-file source architecture replacing monolithic category catalog
- `domain_catalog.yml` — patient pathways, installed capacity indicators, equity dimensions per DAK domain
- `document_ingester.py` — handles user PDFs, explicit URLs, WHO RAG payloads, and WHO MCP stub
- `scoring/assertions.py` — 10 Level 1 checks; output blocked if any fail
- LLM-as-judge rubric with 12 evaluation dimensions (A1–A6 intelligence, B1–B3 HTML, C1–C3 JSON)
- Golden test cases: Zambia ANC, Costa Rica ANC
- Adversarial test case: Yemen ANC (fragile state gate)

### Changed
- `country_taxonomy.yml` redesigned from narrative categories to dimensional ontology (v1.0.0 → v2.0.0)
- `source_hierarchy.yml` redesigned from linear tiers to evidence dimensions (v1.0.0 → v2.0.0)
- `category_catalog.yml` superseded by 3-file split (source_catalog + retrieval_strategy + query_templates)
- Heuristics moved from SKILL.md prose to versioned YAML entries in `donor_signals.yml`
- Risk flags separated into base (5, always evaluated) and emergent (9, evidence-triggered)

### Architecture
- Config layer: 6 YAML files — all logic externalized, no business rules in Python
- Intelligence layer: 5 Python modules, all deterministic, all tested
- Retrieval layer: 6 Python modules with graceful degradation
- Sources layer: 5 files — source catalog, strategy, templates, indicators, domain catalog
- Scoring layer: reliability formula + Level 1 assertions
- Output layer: HTML renderer (source chips) + compact JSON (~55 tokens)

## v1.0.0 — 2026-05-08

### Initial
- 5-country empirical analysis: Zambia, Costa Rica, Italy, China, Switzerland
- Single `category_catalog.yml` with TS/CE/FR/SV/HQ categories
- Block 1 (epidemiological) + Block 2 (digital landscape) structure
- 5 base risk flags + 9 emergent flags from empirical runs
- HTML output with source chips; compact JSON output
- SKILL.md for Claude Project deployment
