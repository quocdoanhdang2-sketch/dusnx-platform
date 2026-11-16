"""Convert the drafted club tiers (datasets/club_sft_v1) into the strict SFT schema.

Emits datasets/club_sft_train_v1/{train,validation}.jsonl plus a DRAFT manifest.
The draft manifest is intentionally not lockable: full training stays blocked by
verify_full_training_gate until a human reviews the review queue, writes the
review receipts and the human_test_attestation.json (see lock_llm_data.py).
Never auto-claims human authorship; every row stays needs_human_review.
"""
import argparse
import hashlib
import json
import random
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "python" / "src"))
sys.path.insert(0, str(REPO_ROOT / "python" / "apps" / "ai_api"))

from dusnx_core.llm_data import audit, digest, write_json  # noqa: E402

TIERS = ("tier1_conversations", "tier2_extractive", "tier3_refuse")


def _contracts(messages, tier):
    contracts = []
    turn = 0
    for message in messages:
        if message["role"] != "assistant":
            continue
        turn += 1
        content = message["content"]
        if tier == 3:
            mode = "acknowledge"  # refusal: no question mark required
        elif any(marker in content.lower() for marker in ("đã nhớ", "đã lưu", "gọi mình", "gọi em", "gọi anh", "gọi chị", "ok, mình sẽ", "rõ rồi")):
            mode = "acknowledge"
        else:
            mode = "answer"
        criteria = ["grounded", "language_compliance"]
        if tier == 3:
            criteria.append("refusal_out_of_scope")
        contracts.append({
            "assistant_turn": turn,
            "response_mode": mode,
            "language": "vi",
            "response_language": "vi",
            "required_facts": [],
            "forbidden_facts": [],
            "future_facts": [],
            "criteria": criteria,
        })
    return contracts


def convert(src_dir: Path, out_dir: Path, val_ratio: float, seed: int):
    rows = []
    seq = 0
    for tier_file in TIERS:
        path = src_dir / f"{tier_file}.jsonl"
        if not path.is_file():
            raise ValueError(f"Missing tier file: {path}")
        tier = int(tier_file[4])
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            seq += 1
            raw = json.loads(line)
            messages = raw["messages"]
            if not messages or messages[0]["role"] != "system":
                raise ValueError(f"{raw['id']}: first message must be the system prompt")
            fam = raw.get("scenario_family", f"club_tier{tier}_{'refuse' if tier == 3 else ('extractive' if tier == 2 else 'conversation')}")
            rows.append({
                "id": raw["id"],
                "source": "synthetic_designed",
                "source_revision": "club-it-v1-draft",
                "license": "CC0-1.0",
                "generation_method": "AI-generated",
                "scenario_family": fam,
                "sequence_id": raw["id"],
                "user_id": f"fictional-club-{seq:04d}",
                "split": "train",  # reassigned below
                "review_status": "needs_human_review",
                "data_kind": "designed_conversation",
                "messages": messages,
                "quality_contracts": _contracts(messages, tier),
            })
    # Group by scenario family so train and validation are partitioned cleanly
    families = sorted(list({r["scenario_family"] for r in rows}))
    rng = random.Random(seed)
    rng.shuffle(families)
    val_fam_count = max(1, int(round(len(families) * val_ratio)))
    val_families = set(families[:val_fam_count])

    val_idx = 0
    train_idx = 0
    for row in rows:
        if row["scenario_family"] in val_families:
            val_idx += 1
            row["split"] = "validation"
            row["user_id"] = f"fictional-club-val-{val_idx:04d}"
            row["scenario_family"] = f"val_{row['scenario_family']}"
        else:
            train_idx += 1
            row["split"] = "train"
            row["user_id"] = f"fictional-club-train-{train_idx:04d}"
            row["scenario_family"] = f"train_{row['scenario_family']}"

    out_dir.mkdir(parents=True, exist_ok=True)
    for split in ("train", "validation"):
        part = [row for row in rows if row["split"] == split]
        with (out_dir / f"{split}.jsonl").open("w", encoding="utf-8", newline="\n") as handle:
            for row in part:
                handle.write(json.dumps(row, ensure_ascii=False) + "\n")

    report = audit({"train": [r for r in rows if r["split"] == "train"],
                    "validation": [r for r in rows if r["split"] == "validation"]},
                   near_duplicate_threshold=0.88)
    manifest = {
        "schema_version": 4,
        "status": "draft_pending_human_review",
        "locked": False,
        "corpus_manifest_sha256": "ba05f53f292b56ba725da1abc725012712f70809ebc00d7ad2b35ab2cc34d7b4",
        "note": "DRAFT. Full SFT stays blocked until human review receipts + human_test_attestation.json exist (lock_llm_data.py). Never train from the draft.",
        "files": {
            "train.jsonl": digest(out_dir / "train.jsonl"),
            "validation.jsonl": digest(out_dir / "validation.jsonl"),
        },
        "row_counts": {"train": report["train"]["records"], "validation": report["validation"]["records"]},
        "audit": report,
        "created": "2026-11-16",
    }
    write_json(out_dir / "manifest.json", manifest)
    print(json.dumps({"total": len(rows), "train": manifest["row_counts"]["train"],
                      "validation": manifest["row_counts"]["validation"],
                      "train_sha256": manifest["files"]["train.jsonl"][:16]}, ensure_ascii=False))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--src", default=str(REPO_ROOT / "datasets" / "club_sft_v1"))
    parser.add_argument("--out", default=str(REPO_ROOT / "datasets" / "club_sft_train_v1"))
    parser.add_argument("--val-ratio", type=float, default=0.1)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()
    convert(Path(args.src), Path(args.out), args.val_ratio, args.seed)


if __name__ == "__main__":
    main()
