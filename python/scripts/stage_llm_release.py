"""Stage a reviewed, unlocked SFT release plus a human-authored independent test."""
import argparse
import json
import shutil
from pathlib import Path

from dusnx_core.llm_data import (
    PROTECTED_PATH_PARTS,
    completion_rows,
    digest,
    read_sft,
    verify_file_manifest,
    verify_train_validation_lineage_receipt,
    write_json,
)

EXPECTED_RELEASE_STATUS = "human_reviewed_supplement_pending_independent_test"
LINEAGE_ARTIFACTS = (
    "lineage_parent_manifest.json",
    "lineage_parent_train_validation_review_receipt.json",
    "lineage_parent_train.jsonl",
    "lineage_parent_validation.jsonl",
    "supplement_review_receipt.json",
    "supplement_review.csv",
)
REQUIRED_ARTIFACTS = (
    "train.jsonl",
    "validation.jsonl",
    "train_validation_review_receipt.json",
    "release_manifest.json",
    *LINEAGE_ARTIFACTS,
)


def _json(path):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"Invalid JSON artifact: {Path(path).name}") from exc


def _regular(path):
    path = Path(path)
    if path.is_symlink() or not path.is_file():
        raise ValueError(f"Missing or unsafe artifact: {path.name}")
    return path


def _jsonl(path):
    path = _regular(path)
    try:
        return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid JSONL artifact: {path.name}") from exc


def _completion_count(rows):
    return len(completion_rows(rows))


def _validate_test(path, expected_test_hash=None):
    rows = read_sft(path, "test")
    if expected_test_hash is not None and digest(path) != expected_test_hash:
        raise ValueError("Independent test changed while staging")
    if not rows:
        raise ValueError("Independent test is empty")
    if any(row["source"] != "human_designed" or row["generation_method"] != "human-authored" for row in rows):
        raise ValueError("Independent test must be human-authored")
    if any(row["review_status"] != "needs_human_review" for row in rows):
        raise ValueError("Independent test must still be needs_human_review before review")
    sequences = {row["sequence_id"] for row in rows}
    if not 6 <= len(sequences) <= 12:
        raise ValueError("Independent test must contain 6-12 distinct sequences")
    return rows


def stage_release(release, output, test_path):
    """Copy a reviewed release and test into a new, unlocked gate directory."""
    release = Path(release).resolve()
    output = Path(output).resolve()
    test_path = Path(test_path).resolve()
    if any(part in str(output).casefold() for part in PROTECTED_PATH_PARTS):
        raise ValueError("Protected staging directory")
    if output.exists():
        raise ValueError("Staging output must not exist")
    if output == release or release in output.parents:
        raise ValueError("Staging output must be outside the release")
    for name in REQUIRED_ARTIFACTS:
        _regular(release / name)

    release_manifest = _json(release / "release_manifest.json")
    if release_manifest.get("status") != EXPECTED_RELEASE_STATUS:
        raise ValueError("Release is not pending an independent test")
    if release_manifest.get("locked") is not False:
        raise ValueError("Release must remain unlocked before staging")
    if release_manifest.get("training_allowed") is not False:
        raise ValueError("Release must not allow training before the human gate")
    if release_manifest.get("official_evaluation_allowed") is not False:
        raise ValueError("Release must not allow official evaluation before the human gate")
    if release_manifest.get("contains_test_split") is not False:
        raise ValueError("Release already contains a test split")

    release_hashes = {name: digest(release / name) for name in ("train.jsonl", "validation.jsonl")}
    if release_manifest.get("release_file_sha256") != release_hashes:
        raise ValueError("Release file hashes do not match release_manifest.json")

    train_rows = _jsonl(release / "train.jsonl")
    validation_rows = _jsonl(release / "validation.jsonl")
    row_counts = {
        "train": _completion_count(train_rows),
        "validation": _completion_count(validation_rows),
    }
    aggregate = _json(release / "train_validation_review_receipt.json")
    verify_train_validation_lineage_receipt(
        release,
        aggregate,
        release_hashes,
        row_counts["train"] + row_counts["validation"],
    )

    test_hash = digest(_regular(test_path))
    test_rows = _validate_test(test_path, test_hash)
    row_counts["test"] = _completion_count(test_rows)

    output.mkdir(parents=True)
    try:
        for name in REQUIRED_ARTIFACTS:
            shutil.copyfile(release / name, output / name)
        verification = release / "lineage_receipt_verification.json"
        if verification.is_file() and not verification.is_symlink():
            shutil.copyfile(verification, output / verification.name)
        shutil.copyfile(test_path, output / "test.jsonl")
        for name, expected in release_hashes.items():
            if digest(output / name) != expected:
                raise ValueError(f"Copied artifact hash mismatch: {name}")
        if digest(output / "test.jsonl") != test_hash:
            raise ValueError("Copied independent test hash mismatch")

        files = {name: digest(output / name) for name in ("train.jsonl", "validation.jsonl", "test.jsonl")}
        manifest = {
            "schema_version": 1,
            "status": "human_authored_test_pending_review",
            "locked": False,
            "training_allowed": False,
            "official_evaluation_allowed": False,
            "source_revision": "v3-human-reviewed-plus-human-test",
            "note": "Staging checksum envelope only; not a human review or attestation. Replaced by schema 4 at lock.",
            "row_counts": row_counts,
            "files": files,
        }
        write_json(output / "manifest.json", manifest)
        verify_file_manifest(output, manifest)
    except Exception:
        shutil.rmtree(output, ignore_errors=True)
        raise

    return {
        "status": "staged",
        "output": str(output),
        "release": str(release),
        "test_sequences": len({row["sequence_id"] for row in test_rows}),
        "row_counts": row_counts,
        "files": files,
        "note": "Pending human review; no attestation created.",
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--release", required=True, help="Unlocked v3 release directory")
    parser.add_argument("--test", required=True, help="Human-authored independent_test.jsonl")
    parser.add_argument("--output", required=True, help="New gate directory, e.g. datasets/llm_sft_v3")
    args = parser.parse_args()
    print(json.dumps(stage_release(args.release, args.output, args.test), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
