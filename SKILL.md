---
name: expo-data-governance
description: Use when turning exhibitor, booth, event, organizer, registry, brochure, or official-site data into a traceable knowledge base, especially when sources conflict, entity IDs drift, rows disappear, PII may leak, or someone proposes patching a derived index directly.
---

# Expo Data Governance

## Overview

Build expo knowledge data as an auditable release, not a merged spreadsheet.
Facts move downstream only through explicit field authority and source lineage;
indexes, chunks, and embeddings are always derived artifacts.

## Workflow

1. Inventory every source and classify each field as public, restricted, or
   discarded. Preserve raw inputs unchanged and record hashes.
2. Define field-level authority before matching. Read
   [source authority](references/source-authority.md) when sources overlap.
3. Stage each row with `source_id`, source coordinates, raw values, and normalized
   candidate keys. Physically quarantine restricted fields; do not place phone
   numbers or personal fields in public retrieval, embeddings, logs, or prompts.
4. Resolve identities through a versioned stable-ID registry. Normalized or fuzzy
   names generate candidates only. Enrichment sources cannot create exhibitors or
   overwrite identity, participation, hall, booth, time, or location facts.
5. Keep ambiguous and unmatched records as explicit review outputs. Do not issue
   provisional stable IDs to unresolved identities. Never recycle IDs.
6. Build canonical fact and relationship tables with source-row lineage. Correct
   upstream facts or use a versioned, evidenced override; never hand-edit an index.
7. Derive chunks and indexes from canonical tables. A scoped rebuild is allowed
   only when dependency coverage is proven and the full release gates and manifest
   are regenerated.
8. Run the gates in [release gates](references/release-gates.md), then execute:

   ```bash
   python scripts/validate_governance.py governance-manifest.json
   ```

Publish only if validation passes and a clean rerun is deterministic.

## Decision Rules

| Situation | Required outcome |
| --- | --- |
| Organizer and registry disagree | Keep the authoritative field; report conflict |
| Fuzzy match is plausible | Preserve as candidate; do not attach facts |
| Restricted data seems useful | Keep it outside the public knowledge product |
| Stable identity is unresolved | Quarantine; do not allocate a stable ID |
| Derived index contains a bad fact | Fix upstream or add an auditable override, then rebuild |
| Gate cannot finish before launch | Keep the last trusted release or suppress the affected fact |

## Common Mistakes

- Treating normalization as identity resolution.
- Letting a richer secondary source override a thinner authoritative source.
- Counting dropped rows as “cleaning” instead of reconciling every disposition.
- Editing chunks, vectors, or caches as if they were facts.
- Validating only the changed partition without regenerating release evidence.
