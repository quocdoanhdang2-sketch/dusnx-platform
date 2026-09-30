"""Human review packages for SFT data; never attests on a person's behalf."""
from __future__ import annotations

import csv
from datetime import datetime
import json
from pathlib import Path

from .llm_data import audit, completion_rows, digest, read_sft, write_json


FIELDS = (
    "review_key", "split", "record_id", "assistant_turn", "prefix_json",
    "reference_answer", "quality_contract_json", "decision", "revised_answer",
    "revised_quality_contract_json", "reviewer", "reviewed_at", "reason",
)


def _json(value):
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def _review_rows(records, split):
    rows = []
    for record in records:
        for pair, contract in zip(completion_rows([record]), record["quality_contracts"]):
            rows.append({
                "review_key": f"{split}:{record['id']}:{pair['assistant_turn']}",
                "split": split,
                "record_id": record["id"],
                "assistant_turn": str(pair["assistant_turn"]),
                "prefix_json": _json(pair["prompt"]),
                "reference_answer": pair["completion"][0]["content"],
                "quality_contract_json": _json(contract),
                "decision": "",
                "revised_answer": "",
                "revised_quality_contract_json": "",
                "reviewer": "",
                "reviewed_at": "",
                "reason": "",
            })
    return rows


def export_package(data_root, output, splits, human_author=None, human_authored_at=None):
    root, out = Path(data_root), Path(output)
    splits = tuple(splits)
    if splits not in (("train", "validation"), ("test",)):
        raise ValueError("Export exactly train+validation or test")
    if out.exists() and any(out.iterdir()):
        raise ValueError("Review output must be empty")
    records = {split: read_sft(root / f"{split}.jsonl", split) for split in splits}
    if splits == ("test",):
        if not str(human_author or "").strip():
            raise ValueError("Test export requires the real human author identifier")
        if not str(human_authored_at or "").strip():
            raise ValueError("Test export requires the human author timestamp")
        human_authored_at = _timestamp(str(human_authored_at).strip())
        if str(human_author).startswith("test-only-"):
            raise ValueError("Test-only identities cannot create a real review package")
        if any(row["source"] != "human_designed" or row["generation_method"] != "human-authored" for row in records["test"]):
            raise ValueError("Replace the AI draft with genuinely human-authored test records first")
    rows = [item for split in splits for item in _review_rows(records[split], split)]
    out.mkdir(parents=True, exist_ok=True)
    csv_path = out / "review.csv"
    with csv_path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS)
        writer.writeheader(); writer.writerows(rows)
    markdown = ["# Gói duyệt SFT", "", "Đọc từng mục ở đây và điền quyết định vào `review.csv`. Không sửa các cột nguồn.", ""]
    for row in rows:
        markdown.extend([f"## {row['review_key']}", "", "**Prefix trước lượt assistant:**", ""])
        for message in json.loads(row["prefix_json"]):
            markdown.append(f"- **{message['role']}**: {message['content']}")
        markdown.extend(["", "**Đáp án mẫu:**", "", row["reference_answer"], "", "**Quality contract:**", "", f"```json\n{row['quality_contract_json']}\n```", ""])
    (out / "review.md").write_text("\n".join(markdown), encoding="utf-8", newline="\n")
    write_json(out / "review_manifest.json", {
        "schema_version": 1,
        "review_type": "train_validation" if splits != ("test",) else "independent_test",
        "splits": list(splits),
        "human_author": str(human_author).strip() if human_author else None,
        "human_authored_at": human_authored_at,
        "source_files": {f"{split}.jsonl": digest(root / f"{split}.jsonl") for split in splits},
        "expected_review_keys": [row["review_key"] for row in rows],
        "row_count": len(rows),
        "instructions": "Fill decision=approve or revise, reviewer, reviewed_at (ISO-8601 with timezone), and reason for every revision. Do not edit source columns.",
    })
    return len(rows)


def _timestamp(value):
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("reviewed_at must be ISO-8601") from exc
    if parsed.tzinfo is None:
        raise ValueError("reviewed_at must include a timezone")
    return parsed.isoformat()


def _write_jsonl(path, rows):
    target = Path(path)
    temporary = target.with_suffix(target.suffix + ".tmp")
    temporary.write_text("".join(_json(row) + "\n" for row in rows), encoding="utf-8", newline="\n")
    temporary.replace(target)


def apply_package(data_root, package, reviewed_csv=None, allow_test_identities=False):
    root, package = Path(data_root), Path(package)
    manifest = json.loads((package / "review_manifest.json").read_text(encoding="utf-8"))
    splits = tuple(manifest["splits"])
    expected_type = "train_validation" if splits == ("train", "validation") else "independent_test"
    if manifest.get("review_type") != expected_type:
        raise ValueError("Review type/splits mismatch")
    for name, expected in manifest["source_files"].items():
        if digest(root / name) != expected:
            raise ValueError(f"SFT source changed after review export: {name}")
    source_rows = {split: read_sft(root / f"{split}.jsonl", split) for split in splits}
    originals = {row["review_key"]: row for split in splits for row in _review_rows(source_rows[split], split)}
    path = Path(reviewed_csv) if reviewed_csv else package / "review.csv"
    with path.open(encoding="utf-8-sig", newline="") as handle:
        submitted = list(csv.DictReader(handle))
    keys = [row.get("review_key", "") for row in submitted]
    if len(keys) != len(set(keys)):
        raise ValueError("Duplicate review key")
    if set(keys) != set(manifest["expected_review_keys"]) or len(submitted) != manifest["row_count"]:
        raise ValueError("Missing or unknown review row")
    reviewers, timestamps = set(), []
    for row in submitted:
        original = originals[row["review_key"]]
        for field in ("split", "record_id", "assistant_turn", "prefix_json", "reference_answer", "quality_contract_json"):
            if row.get(field) != original[field]:
                raise ValueError(f"Immutable review column changed: {row['review_key']} {field}")
        decision = row.get("decision", "").strip().casefold()
        if decision not in {"approve", "revise"}:
            raise ValueError("Every row needs decision=approve or revise")
        reviewer = row.get("reviewer", "").strip()
        if not reviewer:
            raise ValueError("Every row needs a reviewer")
        if reviewer.startswith("test-only-") and not allow_test_identities:
            raise ValueError("Test-only reviewer identity is not valid for real review")
        if expected_type == "independent_test" and reviewer == manifest.get("human_author"):
            raise ValueError("Independent test reviewer must differ from its human author")
        reviewers.add(reviewer); timestamps.append(_timestamp(row.get("reviewed_at", "").strip()))
        if decision == "revise" and (not row.get("reason", "").strip() or not row.get("revised_answer", "").strip()):
            raise ValueError("A revision needs a reason and revised answer")
    submitted_by_key = {row["review_key"]: row for row in submitted}
    updated = {}
    for split, records in source_rows.items():
        for record in records:
            assistant_index = 0
            for message in record["messages"]:
                if message["role"] != "assistant":
                    continue
                assistant_index += 1
                review = submitted_by_key[f"{split}:{record['id']}:{assistant_index}"]
                if review["decision"].strip().casefold() == "revise":
                    message["content"] = review["revised_answer"].strip()
                    revised_contract = review.get("revised_quality_contract_json", "").strip()
                    if revised_contract:
                        record["quality_contracts"][assistant_index - 1] = json.loads(revised_contract)
            record["review_status"] = "human_reviewed"
        updated[split] = records
    all_rows = {split: updated.get(split) or read_sft(root / f"{split}.jsonl", split) for split in ("train", "validation", "test")}
    audit(all_rows)
    for split, records in updated.items():
        _write_jsonl(root / f"{split}.jsonl", records)
    current = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    files = {f"{split}.jsonl": digest(root / f"{split}.jsonl") for split in ("train", "validation", "test")}
    all_reviewed = all(row["review_status"] == "human_reviewed" for rows in all_rows.values() for row in rows)
    current.update(status="human_review_complete_pending_lock" if all_reviewed else "partial_human_review_pending", files=files)
    write_json(root / "manifest.json", current)
    receipt = {
        "schema_version": 1,
        "review_type": expected_type,
        "test_only": bool(allow_test_identities),
        "human_author": manifest.get("human_author"),
        "human_authored_at": manifest.get("human_authored_at"),
        "reviewers": sorted(reviewers),
        "reviewed_at": sorted(set(timestamps)),
        "row_count": len(submitted),
        "result_files": {f"{split}.jsonl": files[f"{split}.jsonl"] for split in splits},
    }
    write_json(package / "review_receipt.json", receipt)
    return receipt
