"""Synthetic fixtures only: never opens repository test/holdout or asserts human review."""

import csv
import hashlib
import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "check_llm_v2_review.py"
spec = importlib.util.spec_from_file_location("review_precheck", SCRIPT)
precheck = importlib.util.module_from_spec(spec)
spec.loader.exec_module(precheck)
FIELDS = [
    "review_key",
    *precheck.IMMUTABLE_FIELDS,
    "decision",
    "revised_answer",
    "revised_quality_contract_json",
    "reviewer",
    "reviewed_at",
    "reason",
]


class ReviewPrecheckTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(
            prefix="synthetic-review-precheck-"
        )
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.package = self.root / "package"
        self.data = self.root / "data"
        self.package.mkdir()
        self.data.mkdir()
        self.rows = []
        for split, count in (("train", 100), ("validation", 24)):
            records = [
                {
                    "id": f"fixture-{split}-{i}",
                    "messages": [
                        {"role": "system", "content": "Synthetic fixture only"},
                        {"role": "user", "content": f"Synthetic prompt {i}"},
                        {"role": "assistant", "content": f"Synthetic answer {i}"},
                    ],
                    "quality_contracts": [
                        {"assistant_turn": 1, "response_mode": "answer"}
                    ],
                }
                for i in range(count)
            ]
            payload = (
                "\n".join(json.dumps(record) for record in records) + "\n"
            ).encode()
            (self.data / f"{split}.jsonl").write_bytes(payload)
            for key, values in precheck.source_review_rows(payload, split).items():
                self.rows.append(
                    dict.fromkeys(FIELDS, "") | values | {"review_key": key}
                )
        self.manifest = {
            "schema_version": 1,
            "review_type": "train_validation",
            "splits": ["train", "validation"],
            "row_count": 124,
            "expected_review_keys": [row["review_key"] for row in self.rows],
            "source_files": {
                name: hashlib.sha256((self.data / name).read_bytes()).hexdigest()
                for name in ("train.jsonl", "validation.jsonl")
            },
        }
        self.save()

    def save(self):
        (self.package / "review_manifest.json").write_text(
            json.dumps(self.manifest), encoding="utf-8"
        )
        with (self.package / "review.csv").open(
            "w", encoding="utf-8-sig", newline=""
        ) as handle:
            writer = csv.DictWriter(handle, fieldnames=FIELDS)
            writer.writeheader()
            writer.writerows(self.rows)

    def complete_fixture_fields(self):
        # These are temporary fixture fields, not a receipt or an attestation.
        for row in self.rows:
            row.update(
                decision="approve",
                reviewer="synthetic-fixture-only",
                reviewed_at="2026-10-31T01:00:00+07:00",
            )
        self.save()

    def inspect(self):
        result = precheck.inspect(self.root, "package", "data", "b8c0a71")
        self.assertFalse(result["training_authorized_by_this_check"])
        self.assertFalse(result["human_authenticity_verified"])
        return result

    def test_blank_package_has_124_incomplete_rows(self):
        result = self.inspect()
        self.assertEqual(result["review"]["decision_counts"]["missing_or_invalid"], 124)
        self.assertTrue(result["source_columns_unchanged"])

    def test_complete_fields_never_authorize_training(self):
        self.complete_fixture_fields()
        self.assertEqual(
            self.inspect()["review_precheck"], "STRUCTURALLY_COMPLETE_ONLY"
        )

    def test_revision_requires_both_answer_and_reason(self):
        self.complete_fixture_fields()
        self.rows[0]["decision"] = "revise"
        self.save()
        issues = self.inspect()["review"]["issue_counts"]
        self.assertEqual(issues["reason_missing"], 1)
        self.assertEqual(issues["revised_answer_missing"], 1)

    def test_timestamp_requires_timezone(self):
        self.complete_fixture_fields()
        self.rows[0]["reviewed_at"] = "2026-10-31T01:00:00"
        self.save()
        self.assertEqual(
            self.inspect()["review"]["issue_counts"][
                "reviewed_at_missing_or_without_timezone"
            ],
            1,
        )

    def test_source_change_requires_new_export(self):
        self.complete_fixture_fields()
        with (self.data / "train.jsonl").open("ab") as handle:
            handle.write(b"\n")
        self.assertEqual(
            self.inspect()["review"]["source_hash_checks_train_validation_only"][
                "train"
            ],
            "SOURCE_CHANGED_SINCE_EXPORT",
        )

    def test_csv_source_column_edits_are_detected(self):
        self.complete_fixture_fields()
        self.rows[0]["reference_answer"] = "Changed immutable answer"
        self.save()
        result = self.inspect()
        self.assertFalse(result["source_columns_unchanged"])
        self.assertEqual(
            result["review"]["issue_counts"]["immutable_source_columns_changed"], 1
        )

    def test_duplicate_keys_are_rejected(self):
        self.complete_fixture_fields()
        self.rows[0]["review_key"] = self.rows[1]["review_key"]
        self.save()
        self.assertFalse(self.inspect()["review"]["keys_unique_and_match_manifest"])

    def test_wrong_manifest_rejected_before_reading_csv(self):
        self.manifest["splits"] = ["test"]
        self.save()
        (self.package / "review.csv").write_bytes(b"not a CSV")
        self.assertTrue(
            self.inspect()["review_precheck"].startswith("UNSUPPORTED_MANIFEST")
        )

    def test_protected_inputs_are_never_opened(self):
        for name in ("test.jsonl", "test_draft.jsonl", "holdout_v3.jsonl"):
            # A directory cannot be read as a file, so an accidental access fails.
            (self.data / name).mkdir()
        self.assertEqual(self.inspect()["review"]["actual_rows"], 124)

    def test_cli_is_read_only_and_redacts_review_contents(self):
        before = {
            p.relative_to(self.root): p.read_bytes()
            for p in self.root.rglob("*")
            if p.is_file()
        }
        run = subprocess.run(
            [
                sys.executable,
                str(SCRIPT),
                "--repo",
                str(self.root),
                "--package",
                "package",
                "--data",
                "data",
            ],
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(run.returncode, 2)
        self.assertEqual(json.loads(run.stdout)["review"]["actual_rows"], 124)
        self.assertNotIn("Synthetic prompt", run.stdout)
        after = {
            p.relative_to(self.root): p.read_bytes()
            for p in self.root.rglob("*")
            if p.is_file()
        }
        self.assertEqual(before, after)

    def test_malformed_input_error_does_not_echo_contents(self):
        (self.package / "review_manifest.json").write_text(
            "private-fixture-sentinel", encoding="utf-8"
        )
        run = subprocess.run(
            [
                sys.executable,
                str(SCRIPT),
                "--repo",
                str(self.root),
                "--package",
                "package",
                "--data",
                "data",
            ],
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(run.returncode, 2)
        self.assertEqual(json.loads(run.stdout)["review_precheck"], "CHECK_FAILED")
        self.assertNotIn("private-fixture-sentinel", run.stdout + run.stderr)

    def test_duplicate_csv_columns_are_rejected(self):
        path = self.package / "review.csv"
        path.write_text(
            path.read_text(encoding="utf-8-sig").replace(
                "review_key,", "review_key,review_key,", 1
            ),
            encoding="utf-8",
        )
        self.assertEqual(self.inspect()["review_precheck"], "CSV_COLUMNS_MISSING")

    def test_paths_outside_repository_are_rejected(self):
        with self.assertRaises(ValueError):
            precheck.inspect(self.root, "../outside-package", "data", "b8c0a71")


if __name__ == "__main__":
    unittest.main()
