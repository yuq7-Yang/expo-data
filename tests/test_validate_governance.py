from __future__ import annotations

import csv
import copy
import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from scripts.validate_governance import validate_manifest


def write_csv(path: Path, rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class GovernanceValidatorTest(unittest.TestCase):
    def make_case(self, root: Path) -> Path:
        source = root / "raw" / "exhibitors.csv"
        table = root / "curated" / "exhibitors.csv"
        index = root / "index" / "chunks.csv"
        write_csv(source, [{"name": "A"}, {"name": "B"}])
        write_csv(
            table,
            [
                {"entity_id": "ex_1", "name": "A", "source_id": "organizer", "source_row": "2"},
                {"entity_id": "ex_2", "name": "B", "source_id": "organizer", "source_row": "3"},
            ],
        )
        write_csv(index, [{"chunk_id": "c1", "entity_id": "ex_1"}])
        manifest = {
            "manifest_version": 1,
            "public_forbidden_columns": ["phone", "legal_representative"],
            "sources": [
                {
                    "id": "organizer",
                    "path": "raw/exhibitors.csv",
                    "sha256": sha256(source),
                    "authority": "identity-placement",
                }
            ],
            "tables": [
                {
                    "id": "exhibitors",
                    "path": "curated/exhibitors.csv",
                    "primary_key": ["entity_id"],
                    "lineage_columns": ["source_id", "source_row"],
                    "forbidden_columns": ["phone", "legal_representative"],
                }
            ],
            "coverage": [
                {
                    "source_id": "organizer",
                    "table_id": "exhibitors",
                    "table_source_id_column": "source_id",
                    "table_source_row_column": "source_row",
                    "source_row_start": 2,
                }
            ],
            "indexes": [
                {
                    "path": "index/chunks.csv",
                    "entity_id_column": "entity_id",
                    "entity_table_id": "exhibitors",
                }
            ],
        }
        path = root / "governance-manifest.json"
        path.write_text(json.dumps(manifest), encoding="utf-8")
        return path

    def test_valid_manifest_passes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(validate_manifest(self.make_case(Path(tmp))), [])

    def test_detects_hash_mismatch_and_forbidden_columns(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            manifest_path = self.make_case(root)
            source = root / "raw" / "exhibitors.csv"
            source.write_text("name\nchanged\n", encoding="utf-8")
            table = root / "curated" / "exhibitors.csv"
            write_csv(
                table,
                [{"entity_id": "ex_1", "source_id": "organizer", "source_row": "2", "phone": "123"}],
            )
            errors = validate_manifest(manifest_path)
            self.assertTrue(any("SHA-256" in error for error in errors))
            self.assertTrue(any("forbidden column" in error for error in errors))

    def test_detects_duplicate_keys_missing_coverage_and_orphan_index_rows(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            manifest_path = self.make_case(root)
            table = root / "curated" / "exhibitors.csv"
            write_csv(
                table,
                [
                    {"entity_id": "ex_1", "source_id": "organizer", "source_row": "2"},
                    {"entity_id": "ex_1", "source_id": "organizer", "source_row": "2"},
                ],
            )
            write_csv(root / "index" / "chunks.csv", [{"chunk_id": "c9", "entity_id": "ex_missing"}])
            errors = validate_manifest(manifest_path)
            self.assertTrue(any("duplicate primary key" in error for error in errors))
            self.assertTrue(any("source rows not covered" in error for error in errors))
            self.assertTrue(any("orphan entity ID" in error for error in errors))

    def test_rejects_incomplete_and_malformed_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "governance-manifest.json"
            path.write_text('{"manifest_version": 1}', encoding="utf-8")
            errors = validate_manifest(path)
            for section in ("sources", "tables", "coverage", "indexes", "public_forbidden_columns"):
                self.assertTrue(any(section in error for error in errors), section)

            path.write_text(
                json.dumps(
                    {
                        "manifest_version": 1,
                        "public_forbidden_columns": ["phone"],
                        "sources": ["not-an-object"],
                        "tables": [],
                        "coverage": [],
                        "indexes": [],
                    }
                ),
                encoding="utf-8",
            )
            errors = validate_manifest(path)
            self.assertTrue(any("sources[0]" in error for error in errors))

    def test_coverage_is_source_qualified_and_exactly_once(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            manifest_path = self.make_case(root)
            write_csv(
                root / "curated" / "exhibitors.csv",
                [
                    {"entity_id": "ex_1", "source_id": "organizer", "source_row": "2"},
                    {"entity_id": "ex_2", "source_id": "other", "source_row": "3"},
                    {"entity_id": "ex_3", "source_id": "organizer", "source_row": "2"},
                ],
            )
            errors = validate_manifest(manifest_path)
            self.assertTrue(any("duplicate disposition" in error for error in errors))
            self.assertTrue(any("source rows not covered" in error for error in errors))

    def test_rejects_unknown_index_table_and_forbidden_index_columns(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            manifest_path = self.make_case(root)
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["indexes"][0]["entity_table_id"] = "missing"
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
            write_csv(
                root / "index" / "chunks.csv",
                [{"chunk_id": "c1", "entity_id": "ghost", "phone": "123"}],
            )
            errors = validate_manifest(manifest_path)
            self.assertTrue(any("unknown entity table" in error for error in errors))
            self.assertTrue(any("forbidden column" in error and "index" in error for error in errors))

    def test_header_only_forbidden_columns_and_unsafe_paths_are_visible(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            manifest_path = self.make_case(root)
            (root / "index" / "chunks.csv").write_text("chunk_id,entity_id,phone\n", encoding="utf-8")
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["sources"][0]["path"] = "../outside.csv"
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
            errors = validate_manifest(manifest_path)
            self.assertTrue(any("path escapes" in error for error in errors))
            self.assertTrue(any("forbidden column" in error and "index" in error for error in errors))

    def test_nested_manifest_fields_fail_closed_instead_of_coercing_or_crashing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            manifest_path = self.make_case(root)
            original = json.loads(manifest_path.read_text(encoding="utf-8"))
            mutations = [
                ("source id", lambda value: value["sources"][0].__setitem__("id", None)),
                ("primary_key", lambda value: value["tables"][0].__setitem__("primary_key", None)),
                ("source_row_start", lambda value: value["coverage"][0].__setitem__("source_row_start", True)),
                ("sha256", lambda value: value["sources"][0].__setitem__("sha256", "not-a-hash")),
            ]
            for label, mutate in mutations:
                with self.subTest(label=label):
                    manifest = copy.deepcopy(original)
                    mutate(manifest)
                    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
                    errors = validate_manifest(manifest_path)
                    self.assertTrue(errors)
                    self.assertTrue(any(label in error for error in errors), errors)

    def test_rejects_duplicate_coverage_declarations_for_one_source(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            manifest_path = self.make_case(root)
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["coverage"].append(copy.deepcopy(manifest["coverage"][0]))
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
            errors = validate_manifest(manifest_path)
            self.assertTrue(any("duplicate coverage declaration" in error for error in errors))

    def test_truncated_csv_cells_do_not_become_literal_none_values(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            manifest_path = self.make_case(root)
            (root / "curated" / "exhibitors.csv").write_text(
                "entity_id,source_id,source_row\n,organizer\n",
                encoding="utf-8",
            )
            (root / "index" / "chunks.csv").write_text(
                "chunk_id,entity_id\nc1\n",
                encoding="utf-8",
            )
            errors = validate_manifest(manifest_path)
            self.assertTrue(any("empty primary key" in error for error in errors))
            self.assertTrue(any("empty lineage source_row" in error for error in errors))
            self.assertTrue(any("orphan entity ID" in error for error in errors))

    def test_manifest_version_rejects_boolean_true(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            manifest_path = self.make_case(root)
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["manifest_version"] = True
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
            errors = validate_manifest(manifest_path)
            self.assertTrue(any("manifest_version" in error for error in errors))

    def test_disposition_rows_for_undeclared_sources_fail(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            manifest_path = self.make_case(root)
            write_csv(
                root / "curated" / "exhibitors.csv",
                [
                    {"entity_id": "ex_1", "source_id": "organizer", "source_row": "2"},
                    {"entity_id": "ex_2", "source_id": "organizer", "source_row": "3"},
                    {"entity_id": "ex_3", "source_id": "ghost", "source_row": "999"},
                ],
            )
            errors = validate_manifest(manifest_path)
            self.assertTrue(any("undeclared source" in error for error in errors))

    def test_wide_rows_fail_for_public_tables_and_indexes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            manifest_path = self.make_case(root)
            (root / "curated" / "exhibitors.csv").write_text(
                "entity_id,source_id,source_row\nex_1,organizer,2,13800138000\n",
                encoding="utf-8",
            )
            (root / "index" / "chunks.csv").write_text(
                "chunk_id,entity_id\nc1,ex_1,13800138000\n",
                encoding="utf-8",
            )
            errors = validate_manifest(manifest_path)
            self.assertTrue(any("table exhibitors" in error and "column count" in error for error in errors))
            self.assertTrue(any("index index/chunks.csv" in error and "column count" in error for error in errors))

    def test_blank_and_duplicate_csv_headers_fail(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            manifest_path = self.make_case(root)
            (root / "curated" / "exhibitors.csv").write_text(
                "entity_id,source_id,source_id\nex_1,organizer,2\n",
                encoding="utf-8",
            )
            (root / "index" / "chunks.csv").write_text(
                "chunk_id,,entity_id\nc1,x,ex_1\n",
                encoding="utf-8",
            )
            errors = validate_manifest(manifest_path)
            self.assertTrue(any("table exhibitors" in error and "duplicate header" in error for error in errors))
            self.assertTrue(any("index index/chunks.csv" in error and "blank header" in error for error in errors))

    def test_invalid_utf8_fails_closed_for_manifest_and_all_csv_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            manifest_path = root / "governance-manifest.json"
            manifest_path.write_bytes(b"\xff")
            self.assertTrue(any("cannot read valid JSON" in error for error in validate_manifest(manifest_path)))

        targets = [
            ("source", Path("raw/exhibitors.csv"), "source organizer"),
            ("table", Path("curated/exhibitors.csv"), "table exhibitors"),
            ("index", Path("index/chunks.csv"), "index index/chunks.csv"),
        ]
        for label, relative, error_label in targets:
            with self.subTest(label=label), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                manifest_path = self.make_case(root)
                target = root / relative
                target.write_bytes(b"\xff")
                if label == "source":
                    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
                    manifest["sources"][0]["sha256"] = sha256(target)
                    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
                errors = validate_manifest(manifest_path)
                self.assertTrue(any(error_label in error and "cannot read CSV" in error for error in errors))

    def test_unterminated_csv_quote_fails_strict_parsing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            manifest_path = self.make_case(root)
            source = root / "raw" / "exhibitors.csv"
            source.write_text('name\n"unterminated\n', encoding="utf-8")
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["sources"][0]["sha256"] = sha256(source)
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
            errors = validate_manifest(manifest_path)
            self.assertTrue(any("source organizer" in error and "cannot read CSV" in error for error in errors))


if __name__ == "__main__":
    unittest.main()
