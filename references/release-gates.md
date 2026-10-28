# Release gates and governance manifest

## Required release gates

Check these invariants before publishing:

1. Every source file is immutable for the release and its SHA-256 matches.
2. Every public source row has an explicit disposition; required coverage has no gaps.
3. Primary keys are non-empty and unique; stable IDs are not recycled or reassigned.
4. All relationship and index foreign keys resolve.
5. Required lineage fields are present and non-empty.
6. Restricted columns and values are absent from public tables, chunks, prompts,
   logs, and generated answers.
7. Ambiguous matches cannot leak into canonical relationships.
8. Current-versus-previous release diffs are explainable: added, retained,
   inactive, renamed, moved, conflicted, and unresolved.
9. A clean rerun from the same inputs produces identical canonical and manifest
   hashes. When vectors are nondeterministic, pin the model/version and compare
   deterministic pre-vector artifacts plus declared vector metadata.

## Manifest shape used by the validator

```json
{
  "manifest_version": 1,
  "public_forbidden_columns": ["phone", "legal_representative"],
  "sources": [{
    "id": "organizer",
    "path": "raw/exhibitors.csv",
    "sha256": "<64 lowercase hex characters>",
    "authority": "identity-placement"
  }],
  "tables": [{
    "id": "exhibitors",
    "path": "curated/exhibitors.csv",
    "primary_key": ["entity_id"],
    "lineage_columns": ["source_id", "source_row"],
    "forbidden_columns": ["phone", "legal_representative"]
  }],
  "coverage": [{
    "source_id": "organizer",
    "table_id": "exhibitors",
    "table_source_id_column": "source_id",
    "table_source_row_column": "source_row",
    "source_row_start": 2
  }],
  "indexes": [{
    "path": "index/chunks.csv",
    "entity_id_column": "entity_id",
    "entity_table_id": "exhibitors"
  }]
}
```

Paths are relative to the manifest. The bundled validator accepts UTF-8 CSV,
checks path containment, source hashes, primary keys, lineage, forbidden columns,
exactly-once `(source_id, source_row)` disposition coverage, and index-to-table
entity references. Every governed source needs exactly one coverage declaration;
point it to a row-disposition table when canonical relationships are one-to-many. The
global forbidden-column policy applies to public tables and indexes, including
header-only files. CSV parsing fails closed on blank or duplicate headers,
truncated or surplus cells, and disposition rows attributed to undeclared
sources. Domain-specific gates
such as booth syntax or organizer totals remain project tests and must not be
replaced by this generic validator.
