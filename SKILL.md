---
name: who-country-health-profiler
description: >
  Builds a structured profile of a country's health system to support 
  WHO SMART Guidelines DAK localization. Use when asked to understand 
  a country's health infrastructure, digital systems, national protocols, 
  data collection practices, or institutional actors before DAK adaptation 
  begins. Activates for: country profile, health system assessment, DAK 
  readiness, localization preparation, national health context.
license: MIT
compatibility: Model-neutral Agent Skill. Uses open data sources and 
  WHO databases. Optional MCP/FHIR tools may be used when available.
metadata:
  project: "USI NLP WHO SMART Guidelines - Country Localization"
  author: "Marionne Blanco Herrera"
  version: "0.1"
  health-domain: "Immunizations (SMART Immunizations DAK)"
---

# WHO Country Health Profiler

## Purpose
Build a structured, verifiable profile of a country's health system 
to reduce the desk research burden on WHO technical staff before 
DAK adaptation begins. Every field must cite its source. Fields 
without verifiable data return null — never invented values.

## When to use this skill
Use when a user needs to understand a country's health context 
before localizing WHO SMART Guidelines, adapting a DAK, or 
planning a country engagement. This skill supports the front-end 
phase of DAK localization — it is not a clinical decision tool.

## Do not use this skill for
- Clinical decision-making for individual patients
- Producing final national health policy
- Replacing on-the-ground WHO expert assessment
- Generating data that cannot be traced to a verifiable source

## Required inputs
- Country name
- Target health domain (default: immunizations)
- Optional: specific DAK component to focus on

## Data sources to query
In order of priority:
1. WHO Global Health Observatory API (apps.who.int/gho/data/node.main)
2. WHO Global Initiative on Digital Health (GIDH) country profiles
3. World Bank Health Nutrition and Population data
4. Global Burden of Disease (IHME) country profiles
5. Country's official Ministry of Health website
6. UNICEF country immunization data
7. Known implementing partner reports (USAID, Gavi, PAHO)

## Workflow
1. Confirm country name and target domain with user
2. Query health system structure from WHO GHO
3. Identify existing digital health systems (DHIS2, OpenMRS, custom)
4. Locate national immunization protocol or equivalent guidelines
5. Map data collection practices at point of care and reporting level
6. Identify key institutional actors in target domain
7. Flag all fields where data is unavailable or uncertain
8. Produce structured JSON profile with source citations
9. Summarize critical gaps for human expert review

## Output format
Return a structured profile with these sections:

### Health system structure
- Levels of care (primary/secondary/tertiary)
- Referral pathways
- Prescribing authority at each level
- Source + confidence score

### Digital infrastructure
- Existing digital health systems
- Interoperability status
- Connectivity and device access
- Source + confidence score

### National guidelines
- Immunization protocol exists: yes/no
- Alignment with WHO recommendations: aligned/partial/divergent/unknown
- Known divergences (if any)
- Source + confidence score

### Data collection practices
- Data collected at point of care
- Data aggregated for national reporting
- Gaps relative to DAK data elements
- Source + confidence score

### Key institutional actors
- Ministry of Health department responsible
- Active donor organizations
- Implementing partners present
- Digital system vendors
- Source + confidence score

### Critical gaps summary
List of fields that could not be populated from open sources.
These require WHO expert input before DAK adaptation begins.

## Confidence scoring
- High: data from official WHO or government source, current within 3 years
- Medium: data from implementing partner report or academic source
- Low: data inferred or from source older than 3 years
- Null: no verifiable data found — do not invent

## Safety rules
Never generate health system data without a cited source.
If a field cannot be verified, return null and flag it explicitly.
This profile is a starting point for expert review, not a final assessment.
