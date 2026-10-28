# Expo Data Governance Skill

A reusable Codex/Agent Skill for turning exhibitor, booth, event, organizer,
business-registry, brochure, and official-site data into a traceable,
privacy-safe knowledge release.

It captures the hard-won boundaries that ordinary ETL guidance often misses:
field-level source authority, stable identity across batches, physical PII
quarantine, zero-loss reconciliation, auditable corrections, and the rule that
chunks, vectors, and indexes are derived artifacts rather than sources of truth.

## Repository contents

- `SKILL.md` — invocation triggers and the core workflow.
- `references/source-authority.md` — authority, field policy, and stable-ID rules.
- `references/release-gates.md` — release invariants and manifest format.
- `scripts/validate_governance.py` — standard-library manifest validator.
- `tests/` — validator regression tests.
- `evals/` — behavioral scenarios, hidden rubric, and baseline observations.
- `agents/openai.yaml` — Codex UI metadata.

## Install

Clone the repository into a directory scanned for Skills. The directory name may
differ from the Skill name, but using the Skill name is clearest:

```bash
git clone https://github.com/yuq7-Yang/expo-data.git ~/.codex/skills/expo-data-governance
```

The Skill can then be invoked explicitly as `$expo-data-governance` or selected
automatically for matching requests.

## Validate a data release

Create a `governance-manifest.json` using the shape documented in
`references/release-gates.md`, then run:

```bash
python scripts/validate_governance.py governance-manifest.json
```

The command exits nonzero and lists violations when it detects source-hash drift,
duplicate or empty primary keys, missing lineage, forbidden public columns,
missing or duplicate source-row dispositions, unsafe paths, or orphan index
entity IDs. Required manifest sections fail closed when omitted or malformed;
CSV files also fail on blank/duplicate headers, inconsistent row widths, and
disposition rows attributed to undeclared sources.

The validator is intentionally generic. Expo-specific checks such as legal booth
syntax, organizer totals, event schedules, and allowed category vocabularies
belong in the consuming project's tests.

## Development

Run the deterministic tests with the Python standard library:

```bash
python -m unittest discover -s tests -v
```

Behavioral evaluation instructions are in `evals/scenarios.md`. Keep
`evals/rubric.md` hidden from the agent being evaluated, then compare the result
against the rubric and record material deviations.
