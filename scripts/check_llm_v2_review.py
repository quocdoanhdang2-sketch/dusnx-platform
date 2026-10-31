"""Read-only Windows/cloud precheck; never applies reviews or authorizes training.

Python 3.11+ standard library only. Output contains counts, not sample/reviewer contents.
No fetch/pull, no writes, no test/holdout reads, no predictions.
"""

import argparse
import csv
import hashlib
import json
import subprocess
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path

IMMUTABLE_FIELDS = (
    "split",
    "record_id",
    "assistant_turn",
    "prefix_json",
    "reference_answer",
    "quality_contract_json",
)


def source_review_rows(payload, split):
    """Mirror the export's source columns, without importing training dependencies."""
    result = {}
    for line in payload.decode("utf-8").splitlines():
        if not line.strip():
            continue
        record = json.loads(line)
        if not isinstance(record, dict) or not isinstance(record.get("id"), str):
            raise TypeError("Invalid source record")
        messages, contracts = record.get("messages"), record.get("quality_contracts")
        if not isinstance(messages, list) or not isinstance(contracts, list):
            raise TypeError("Invalid source structure")
        turn = 0
        for index, message in enumerate(messages):
            if not isinstance(message, dict):
                raise TypeError("Invalid source message")
            if message.get("role") != "assistant":
                continue
            turn += 1
            key = f"{split}:{record['id']}:{turn}"
            if (
                key in result
                or turn > len(contracts)
                or not isinstance(message.get("content"), str)
            ):
                raise ValueError("Invalid assistant turn")
            result[key] = {
                "split": split,
                "record_id": record["id"],
                "assistant_turn": str(turn),
                "prefix_json": json.dumps(
                    messages[:index], ensure_ascii=False, separators=(",", ":")
                ),
                "reference_answer": message["content"],
                "quality_contract_json": json.dumps(
                    contracts[turn - 1], ensure_ascii=False, separators=(",", ":")
                ),
            }
        if not turn or turn != len(contracts):
            raise ValueError("Quality contracts do not match assistant turns")
    return result


def git(repo, *args):
    result = subprocess.run(
        ["git", "-C", str(repo), *args], check=False, capture_output=True, text=True
    )
    return result.stdout.strip() if result.returncode == 0 else None


def inspect(repo, package, data, expected_main):
    repo = Path(repo).resolve()
    package, data = (repo / package).resolve(), (repo / data).resolve()
    if not package.is_relative_to(repo) or not data.is_relative_to(repo):
        raise ValueError("Package and data must remain inside the repository")
    head = git(repo, "rev-parse", "HEAD")
    status = git(repo, "status", "--porcelain=v1", "--untracked-files=normal")
    expected = git(repo, "rev-parse", "--verify", expected_main + "^{commit}")
    main = git(repo, "rev-parse", "--verify", "refs/remotes/origin/main^{commit}")
    diff = git(repo, "diff", "--name-only", expected) if expected else None
    report = {
        "git": {
            "valid_checkout": head is not None,
            "branch": git(repo, "branch", "--show-current"),
            "head": head,
            "dirty": None if status is None else bool(status),
            "status_entry_count": None if status is None else len(status.splitlines()),
            "expected_main_resolved": expected,
            "cached_origin_main": main,
            "cached_main_matches_expected": None
            if not main or not expected
            else main == expected,
            "working_diff_vs_expected": None if diff is None else bool(diff),
        },
        "package_exists": package.is_dir(),
        "package_files": {
            name: (package / name).is_file()
            for name in (
                "README_NEXT.md",
                "gate_status.json",
                "review_manifest.json",
                "review.csv",
                "review.md",
            )
        },
        "protected_test_read": False,
        "human_authenticity_verified": False,
        "training_authorized_by_this_check": False,
        "full_gate": "NOT_ESTABLISHED: requires real human review, independent test, receipts and official validators",
    }
    manifest_path = package / "review_manifest.json"
    if manifest_path.is_symlink() or (package / "review.csv").is_symlink():
        report["review_precheck"] = "SYMLINK_INPUT_REJECTED"
        return report
    if not manifest_path.is_file():
        report["review_precheck"] = "PACKAGE_OR_MANIFEST_MISSING"
        return report
    manifest = json.loads(manifest_path.read_text(encoding="utf-8-sig"))
    if not isinstance(manifest, dict):
        report["review_precheck"] = "MALFORMED_MANIFEST"
        return report
    if (
        manifest.get("schema_version") != 1
        or manifest.get("review_type") != "train_validation"
        or manifest.get("splits") != ["train", "validation"]
    ):
        report["review_precheck"] = "UNSUPPORTED_MANIFEST: CSV not opened"
        return report
    if not (package / "review.csv").is_file():
        report["review_precheck"] = "CSV_MISSING"
        return report
    expected_keys = manifest.get("expected_review_keys")
    expected_rows = manifest.get("row_count")
    if (
        not isinstance(expected_keys, list)
        or not all(isinstance(k, str) for k in expected_keys)
        or not isinstance(expected_rows, int)
        or isinstance(expected_rows, bool)
    ):
        report["review_precheck"] = "MALFORMED_MANIFEST"
        return report
    with (package / "review.csv").open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        required = {
            "review_key",
            "split",
            "record_id",
            "assistant_turn",
            "prefix_json",
            "reference_answer",
            "quality_contract_json",
            "decision",
            "reviewer",
            "reviewed_at",
            "reason",
            "revised_answer",
            "revised_quality_contract_json",
        }
        columns = reader.fieldnames or []
        if not required.issubset(columns) or len(columns) != len(set(columns)):
            report["review_precheck"] = "CSV_COLUMNS_MISSING"
            return report
        rows = list(reader)
    issues, decisions, bad_rows = Counter(), Counter(), []
    keys = [row.get("review_key", "") for row in rows]
    for index, row in enumerate(rows, 2):
        row_issues = []
        decision = (row.get("decision") or "").strip().casefold()
        decisions[
            decision if decision in {"approve", "revise"} else "missing_or_invalid"
        ] += 1
        if decision not in {"approve", "revise"}:
            row_issues.append("decision_missing_or_invalid")
        reviewer = (row.get("reviewer") or "").strip()
        if not reviewer:
            row_issues.append("reviewer_missing")
        elif reviewer.startswith("test-only-"):
            row_issues.append("test_identity_not_valid_for_real_review")
        try:
            parsed = datetime.fromisoformat((row.get("reviewed_at") or "").strip())
            if parsed.tzinfo is None or parsed.utcoffset() is None:
                raise ValueError()
        except ValueError:
            row_issues.append("reviewed_at_missing_or_without_timezone")
        if decision == "revise":
            for name in ("revised_answer", "reason"):
                if not (row.get(name) or "").strip():
                    row_issues.append(name + "_missing")
        if row.get("split") not in {"train", "validation"}:
            row_issues.append("unexpected_split")
        if None in row or any(row.get(field) is None for field in required):
            row_issues.append("malformed_csv_row")
        for field in (
            "prefix_json",
            "quality_contract_json",
            "revised_quality_contract_json",
        ):
            value = row.get(field) or ""
            if not value.strip() and field == "revised_quality_contract_json":
                continue
            try:
                json.loads(value)
            except (ValueError, TypeError):
                row_issues.append(field + "_invalid_json")
        if row_issues:
            issues.update(row_issues)
            if len(bad_rows) < 20:
                bad_rows.append(index)
    keys_valid = (
        len(keys) == len(set(keys))
        and set(keys) == set(expected_keys)
        and len(rows) == expected_rows == len(expected_keys)
    )
    source_checks, originals = {}, {}
    declared = manifest.get("source_files", {})
    for split in ("train", "validation"):
        filename = split + ".jsonl"
        path = data / filename
        if not path.is_file() or path.is_symlink():
            source_checks[split] = "MISSING_OR_SYMLINK"
        elif not isinstance(declared, dict) or not isinstance(
            declared.get(filename), str
        ):
            source_checks[split] = "HASH_NOT_DECLARED"
        else:
            payload = path.read_bytes()
            digest = hashlib.sha256(payload).hexdigest()
            source_checks[split] = (
                "MATCH"
                if digest == declared[filename]
                else "SOURCE_CHANGED_SINCE_EXPORT"
            )
            if source_checks[split] == "MATCH":
                originals.update(source_review_rows(payload, split))
    source_matches = all(value == "MATCH" for value in source_checks.values())
    immutable_matches = None
    if source_matches:
        immutable_matches = set(originals) == set(expected_keys)
        for row in rows:
            original = originals.get(row.get("review_key"))
            if original is None or any(
                row.get(field) != original[field] for field in IMMUTABLE_FIELDS
            ):
                issues["immutable_source_columns_changed"] += 1
                immutable_matches = False
    ready = (
        not issues
        and keys_valid
        and len(rows) == 124
        and source_matches
        and immutable_matches
    )
    report.update(
        review_precheck="STRUCTURALLY_COMPLETE_ONLY"
        if ready
        else "INCOMPLETE_OR_SOURCE_MISMATCH",
        review={
            "actual_rows": len(rows),
            "manifest_expected_rows": expected_rows,
            "requested_124_rows_match": len(rows) == expected_rows == 124,
            "keys_unique_and_match_manifest": keys_valid,
            "decision_counts": dict(decisions),
            "issue_counts": dict(issues),
            "first_problem_csv_line_numbers": bad_rows,
            "source_hash_checks_train_validation_only": source_checks,
        },
        source_columns_unchanged=immutable_matches,
        full_record_schema="NOT_CHECKED: use the existing official validators after prerequisites are met",
        human_test_and_receipts="NOT_VERIFIED: frozen test content not opened",
    )
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", required=True)
    parser.add_argument(
        "--package", default="runtime/llm-v2-human-gate-20261005-114208"
    )
    parser.add_argument("--data", default="datasets/llm_sft_v2")
    parser.add_argument(
        "--expected-main", default="b8c0a710c4bb8c786669eadc6576b352915e5ed8"
    )
    args = parser.parse_args()
    try:
        report = inspect(args.repo, args.package, args.data, args.expected_main)
    except (ValueError, OSError, TypeError, csv.Error) as exc:
        # Never echo exception text: malformed inputs may contain private content.
        report = {
            "review_precheck": "CHECK_FAILED",
            "error_type": type(exc).__name__,
            "training_authorized_by_this_check": False,
        }
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report.get("review_precheck") == "STRUCTURALLY_COMPLETE_ONLY" else 2


if __name__ == "__main__":
    sys.exit(main())
