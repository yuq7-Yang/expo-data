#!/usr/bin/env python3
"""Validate lineage, privacy, coverage, and index references in a release manifest."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
from collections import Counter
from pathlib import Path
from typing import Any


SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


def _read_csv(
    path: Path, label: str, errors: list[str]
) -> tuple[list[str], list[dict[str, str]]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.reader(handle, strict=True)
        try:
            raw_headers = next(reader)
        except StopIteration:
            errors.append(f"{label}: CSV is empty and has no header")
            return [], []
        headers = [header.strip() for header in raw_headers]
        if any(not header for header in headers):
            errors.append(f"{label}: blank header column")
        duplicates = sorted({header for header in headers if headers.count(header) > 1 and header})
        if duplicates:
            errors.append(f"{label}: duplicate header column(s): {duplicates}")
        rows: list[dict[str, str]] = []
        for row_number, values in enumerate(reader, 2):
            if len(values) != len(headers):
                errors.append(
                    f"{label}: CSV row {row_number} column count {len(values)} "
                    f"does not match header count {len(headers)}"
                )
            normalized = (values + [""] * len(headers))[: len(headers)]
            rows.append(dict(zip(headers, normalized)))
        return headers, rows


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _cell(row: dict[str, str], column: str) -> str:
    value = row.get(column)
    return value.strip() if isinstance(value, str) else ""


def _string_field(
    obj: dict[str, Any], key: str, label: str, errors: list[str]
) -> str | None:
    value = obj.get(key)
    if not isinstance(value, str) or not value.strip():
        errors.append(f"{label}: must be a non-empty string")
        return None
    return value.strip()


def _string_list(
    value: Any, label: str, errors: list[str], *, non_empty: bool
) -> list[str]:
    if not isinstance(value, list) or (non_empty and not value):
        qualifier = "non-empty " if non_empty else ""
        errors.append(f"{label}: must be a {qualifier}list of unique non-empty strings")
        return []
    cleaned: list[str] = []
    for item in value:
        if not isinstance(item, str) or not item.strip():
            errors.append(f"{label}: must contain only non-empty strings")
            continue
        cleaned.append(item.strip())
    if len(set(cleaned)) != len(cleaned):
        errors.append(f"{label}: values must be unique")
    return cleaned


def _resolve(root: Path, relative: Any, label: str, errors: list[str]) -> Path | None:
    if not isinstance(relative, str) or not relative:
        errors.append(f"{label}: missing path")
        return None
    path = (root / relative).resolve()
    try:
        path.relative_to(root.resolve())
    except ValueError:
        errors.append(f"{label}: path escapes manifest directory: {relative}")
        return None
    if not path.is_file():
        errors.append(f"{label}: file not found: {relative}")
        return None
    return path


def validate_manifest(manifest_path: Path | str) -> list[str]:
    path = Path(manifest_path).resolve()
    errors: list[str] = []
    try:
        manifest = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        return [f"manifest: cannot read valid JSON: {exc}"]
    if not isinstance(manifest, dict):
        return ["manifest: top level must be an object"]
    if type(manifest.get("manifest_version")) is not int or manifest.get("manifest_version") != 1:
        errors.append("manifest: manifest_version must be 1")

    required_sections = ("public_forbidden_columns", "sources", "tables", "coverage", "indexes")
    sections: dict[str, list[Any]] = {}
    for name in required_sections:
        value = manifest.get(name)
        if not isinstance(value, list) or not value:
            errors.append(f"manifest: {name} must be a non-empty list")
            sections[name] = []
        else:
            sections[name] = value
    global_forbidden = set(
        _string_list(
            sections["public_forbidden_columns"],
            "manifest public_forbidden_columns",
            errors,
            non_empty=True,
        )
    )

    root = path.parent
    sources: dict[str, dict[str, Any]] = {}
    source_rows: dict[str, list[dict[str, str]]] = {}
    for index, source in enumerate(sections["sources"]):
        if not isinstance(source, dict):
            errors.append(f"manifest: sources[{index}] must be an object")
            continue
        source_id = _string_field(source, "id", f"source id at sources[{index}]", errors)
        _string_field(source, "authority", f"source {source_id or index} authority", errors)
        expected_hash = _string_field(source, "sha256", f"source {source_id or index} sha256", errors)
        if expected_hash is not None and not SHA256_RE.fullmatch(expected_hash):
            errors.append(f"source {source_id or index} sha256: must be 64 lowercase hexadecimal characters")
            expected_hash = None
        if source_id is None:
            continue
        if source_id in sources:
            errors.append(f"source: duplicate id: {source_id!r}")
            continue
        sources[source_id] = source
        source_path = _resolve(root, source.get("path"), f"source {source_id}", errors)
        if source_path is None:
            continue
        actual_hash = _sha256(source_path)
        if expected_hash is not None and expected_hash != actual_hash:
            errors.append(f"source {source_id}: SHA-256 mismatch")
        try:
            _, source_rows[source_id] = _read_csv(source_path, f"source {source_id}", errors)
        except (OSError, UnicodeError, csv.Error) as exc:
            errors.append(f"source {source_id}: cannot read CSV: {exc}")

    tables: dict[str, dict[str, Any]] = {}
    table_rows: dict[str, list[dict[str, str]]] = {}
    table_columns: dict[str, list[str]] = {}
    for index, table in enumerate(sections["tables"]):
        if not isinstance(table, dict):
            errors.append(f"manifest: tables[{index}] must be an object")
            continue
        table_id = _string_field(table, "id", f"table id at tables[{index}]", errors)
        if table_id is None:
            continue
        if table_id in tables:
            errors.append(f"table: duplicate id: {table_id!r}")
            continue
        tables[table_id] = table
        table_path = _resolve(root, table.get("path"), f"table {table_id}", errors)
        if table_path is None:
            continue
        try:
            fieldnames, rows = _read_csv(table_path, f"table {table_id}", errors)
        except (OSError, UnicodeError, csv.Error) as exc:
            errors.append(f"table {table_id}: cannot read CSV: {exc}")
            continue
        table_rows[table_id] = rows
        table_columns[table_id] = fieldnames
        columns = set(fieldnames)
        local_forbidden = _string_list(
            table.get("forbidden_columns"),
            f"table {table_id} forbidden_columns",
            errors,
            non_empty=False,
        )
        forbidden = columns.intersection(global_forbidden.union(local_forbidden))
        if forbidden:
            errors.append(f"table {table_id}: forbidden column(s): {sorted(forbidden)}")
        lineage = _string_list(
            table.get("lineage_columns"),
            f"table {table_id} lineage_columns",
            errors,
            non_empty=True,
        )
        missing_lineage = [column for column in lineage if column not in columns]
        if missing_lineage:
            errors.append(f"table {table_id}: missing lineage column(s): {missing_lineage}")
        for row_number, row in enumerate(rows, 2):
            for column in lineage:
                if column in row and not _cell(row, column):
                    errors.append(f"table {table_id}: empty lineage {column} at CSV row {row_number}")
        primary_key = _string_list(
            table.get("primary_key"),
            f"table {table_id} primary_key",
            errors,
            non_empty=True,
        )
        if primary_key and any(column not in columns for column in primary_key):
            errors.append(f"table {table_id}: primary key column missing")
        elif primary_key:
            seen: set[tuple[str, ...]] = set()
            for row_number, row in enumerate(rows, 2):
                key = tuple(_cell(row, column) for column in primary_key)
                if not all(key):
                    errors.append(f"table {table_id}: empty primary key at CSV row {row_number}")
                elif key in seen:
                    errors.append(f"table {table_id}: duplicate primary key {key}")
                seen.add(key)

    covered_sources: set[str] = set()
    coverage_declarations: Counter[str] = Counter()
    coverage_contracts: dict[str, list[tuple[str, str, str]]] = {}
    for index, coverage in enumerate(sections["coverage"]):
        if not isinstance(coverage, dict):
            errors.append(f"manifest: coverage[{index}] must be an object")
            continue
        source_id = _string_field(coverage, "source_id", f"coverage[{index}] source_id", errors)
        table_id = _string_field(coverage, "table_id", f"coverage[{index}] table_id", errors)
        source_id_column = _string_field(
            coverage, "table_source_id_column", f"coverage[{index}] table_source_id_column", errors
        )
        column = _string_field(
            coverage, "table_source_row_column", f"coverage[{index}] table_source_row_column", errors
        )
        if None in (source_id, table_id, source_id_column, column):
            continue
        coverage_declarations[source_id] += 1
        if coverage_declarations[source_id] > 1:
            errors.append(f"coverage {source_id}: duplicate coverage declaration")
            continue
        if source_id not in source_rows or table_id not in table_rows:
            errors.append(f"coverage: unknown or unreadable source/table {source_id}/{table_id}")
            continue
        covered_sources.add(source_id)
        coverage_contracts.setdefault(table_id, []).append((source_id, source_id_column, column))
        start = coverage.get("source_row_start")
        if type(start) is not int or start < 1:
            errors.append(f"coverage {source_id}->{table_id}: source_row_start must be a positive integer")
            continue
        columns = set(table_columns[table_id])
        missing_columns = [name for name in (source_id_column, column) if name not in columns]
        if missing_columns:
            errors.append(f"coverage {source_id}->{table_id}: missing column(s) {missing_columns}")
            continue
        expected = set(range(start, start + len(source_rows[source_id])))
        counts: Counter[int] = Counter()
        for row in table_rows[table_id]:
            if _cell(row, source_id_column) != source_id:
                continue
            try:
                counts[int(_cell(row, column))] += 1
            except ValueError:
                errors.append(f"coverage {source_id}->{table_id}: non-integer source row")
        missing = sorted(expected - set(counts))
        if missing:
            errors.append(f"coverage {source_id}->{table_id}: source rows not covered: {missing[:20]}")
        duplicates = sorted(row for row, count in counts.items() if count > 1)
        if duplicates:
            errors.append(f"coverage {source_id}->{table_id}: duplicate disposition: {duplicates[:20]}")
        outside = sorted(set(counts) - expected)
        if outside:
            errors.append(f"coverage {source_id}->{table_id}: source rows out of range: {outside[:20]}")
    for source_id in sorted(set(sources) - covered_sources):
        errors.append(f"coverage: source {source_id} has no disposition coverage declaration")
    for table_id, contracts in coverage_contracts.items():
        for row_number, row in enumerate(table_rows[table_id], 2):
            matches = [
                source_id
                for source_id, source_id_column, _ in contracts
                if _cell(row, source_id_column) == source_id
            ]
            if not matches:
                observed = sorted(
                    {
                        _cell(row, source_id_column)
                        for _, source_id_column, _ in contracts
                        if _cell(row, source_id_column)
                    }
                )
                errors.append(
                    f"coverage table {table_id}: CSV row {row_number} has undeclared source "
                    f"{observed or ['<empty>']}"
                )
            elif len(matches) > 1:
                errors.append(
                    f"coverage table {table_id}: CSV row {row_number} matches multiple source declarations"
                )

    for position, index in enumerate(sections["indexes"]):
        if not isinstance(index, dict):
            errors.append(f"manifest: indexes[{position}] must be an object")
            continue
        label = f"index {index.get('path', position)}"
        index_path = _resolve(root, index.get("path"), label, errors)
        table_id = _string_field(
            index, "entity_table_id", f"indexes[{position}] entity_table_id", errors
        )
        entity_column = _string_field(
            index, "entity_id_column", f"indexes[{position}] entity_id_column", errors
        )
        if index_path is None:
            continue
        try:
            fieldnames, rows = _read_csv(index_path, label, errors)
        except (OSError, UnicodeError, csv.Error) as exc:
            errors.append(f"{label}: cannot read CSV: {exc}")
            continue
        columns = set(fieldnames)
        local_forbidden = _string_list(
            index.get("forbidden_columns", []),
            f"{label} forbidden_columns",
            errors,
            non_empty=False,
        )
        forbidden = columns.intersection(global_forbidden.union(local_forbidden))
        if forbidden:
            errors.append(f"{label}: forbidden column(s): {sorted(forbidden)}")
        if table_id is None or entity_column is None:
            continue
        if entity_column not in columns:
            errors.append(f"{label}: missing entity ID column {entity_column!r}")
            continue
        if table_id not in table_rows:
            errors.append(f"{label}: unknown entity table {table_id!r}")
            continue
        table = tables[table_id]
        primary_key = _string_list(
            table.get("primary_key"),
            f"table {table_id} primary_key",
            errors,
            non_empty=True,
        )
        if len(primary_key) != 1:
            errors.append(f"{label}: entity table must have one-column primary key")
            continue
        valid_ids = {
            value
            for row in table_rows[table_id]
            if (value := _cell(row, primary_key[0]))
        }
        for row_number, row in enumerate(rows, 2):
            entity_id = _cell(row, entity_column)
            if entity_id not in valid_ids:
                errors.append(
                    f"{label}: orphan entity ID {entity_id!r} at CSV row {row_number}"
                )

    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--json", action="store_true", help="emit a JSON result")
    args = parser.parse_args()
    errors = validate_manifest(args.manifest)
    if args.json:
        print(json.dumps({"ok": not errors, "errors": errors}, ensure_ascii=False, indent=2))
    elif errors:
        print("governance validation failed:")
        for error in errors:
            print(f"- {error}")
    else:
        print("governance validation passed")
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
