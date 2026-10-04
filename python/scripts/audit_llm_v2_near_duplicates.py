"""Audit the AI-draft LLM v2 split and produce a human rewrite queue.

This tool is read-only: it never edits data, review status, manifests, or receipts.
It intentionally mirrors ``dusnx_core.llm_data.near_similarity`` without importing
the package so the audit can run in a minimal Python environment without PyTorch.
"""
from __future__ import annotations

import argparse
import csv
from difflib import SequenceMatcher
import json
from pathlib import Path
import re
import unicodedata


def normalized(value: str) -> str:
    return " ".join(unicodedata.normalize("NFC", value).casefold().split())


def words(value: str) -> list[str]:
    return re.findall(r"\w+", normalized(value), flags=re.UNICODE)


def ngrams(value: str, size: int = 3) -> set[tuple[str, ...]]:
    tokens = words(value)
    return {tuple(tokens[index:index + size]) for index in range(max(0, len(tokens) - size + 1))}


def near_similarity(left: str, right: str) -> float:
    left, right = normalized(left), normalized(right)
    sequence = SequenceMatcher(None, left, right).ratio()
    left_grams, right_grams = ngrams(left), ngrams(right)
    union = left_grams | right_grams
    jaccard = len(left_grams & right_grams) / len(union) if union else 0.0
    return max(sequence, jaccard)


def prompt_signature(messages: list[dict]) -> str:
    pieces: list[str] = []
    for message in messages:
        if message["role"] == "system" and "Bối cảnh giả lập:" in message["content"]:
            pieces.append(message["content"].split("Bối cảnh giả lập:", 1)[1])
        elif message["role"] == "user":
            pieces.append(message["content"])
    return normalized(" ".join(pieces))


def read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", type=Path, default=Path("datasets/llm_sft_v2"))
    parser.add_argument("--threshold", type=float, default=0.82)
    parser.add_argument("--output", type=Path, default=Path("runtime/llm-v2-near-duplicate-audit"))
    args = parser.parse_args()

    files = {"train": "train.jsonl", "validation": "validation.jsonl", "test": "test_draft.jsonl"}
    prompts: list[dict] = []
    records: dict[tuple[str, str], dict] = {}
    for split, filename in files.items():
        for row in read_jsonl(args.data / filename):
            records[(split, row["id"])] = row
            turn = 0
            for index, message in enumerate(row["messages"]):
                if message["role"] != "assistant":
                    continue
                turn += 1
                prompts.append({
                    "split": split,
                    "id": row["id"],
                    "assistant_turn": turn,
                    "signature": prompt_signature(row["messages"][:index]),
                })

    cross_pairs: list[dict] = []
    within_pairs: list[dict] = []
    max_cross_split_similarity = 0.0
    adjacency: dict[tuple[str, str], set[tuple[str, str]]] = {}
    for index, left in enumerate(prompts):
        for right in prompts[index + 1:]:
            score = near_similarity(left["signature"], right["signature"])
            same_split = left["split"] == right["split"]
            if not same_split:
                max_cross_split_similarity = max(max_cross_split_similarity, score)
            if score < args.threshold:
                continue
            pair = {
                "score": round(score, 4),
                "left_split": left["split"], "left_id": left["id"],
                "left_assistant_turn": left["assistant_turn"],
                "right_split": right["split"], "right_id": right["id"],
                "right_assistant_turn": right["assistant_turn"],
            }
            (within_pairs if same_split else cross_pairs).append(pair)
            left_key, right_key = (left["split"], left["id"]), (right["split"], right["id"])
            adjacency.setdefault(left_key, set()).add(right_key)
            adjacency.setdefault(right_key, set()).add(left_key)

    components: list[list[tuple[str, str]]] = []
    seen: set[tuple[str, str]] = set()
    for start in adjacency:
        if start in seen:
            continue
        stack, component = [start], []
        seen.add(start)
        while stack:
            current = stack.pop()
            component.append(current)
            for neighbor in adjacency[current]:
                if neighbor not in seen:
                    seen.add(neighbor)
                    stack.append(neighbor)
        components.append(component)
    components.sort(key=len, reverse=True)
    component_by_record = {
        key: component_index
        for component_index, component in enumerate(components, 1)
        for key in component
    }

    args.output.mkdir(parents=True, exist_ok=True)
    with (args.output / "cross_split_pairs.csv").open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(cross_pairs[0]) if cross_pairs else ["score"])
        writer.writeheader()
        writer.writerows(sorted(cross_pairs, key=lambda pair: pair["score"], reverse=True))
    with (args.output / "within_split_pairs.csv").open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(within_pairs[0]) if within_pairs else ["score"])
        writer.writeheader()
        writer.writerows(sorted(within_pairs, key=lambda pair: pair["score"], reverse=True))

    with (args.output / "rewrite_queue.csv").open("w", encoding="utf-8-sig", newline="") as handle:
        fields = ["cluster", "split", "id", "scenario_family", "language", "max_cross_split_similarity",
                  "user_prompt", "assistant_answer", "human_rewrite", "human_notes"]
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for key in sorted(adjacency):
            split, record_id = key
            row = records[key]
            related_scores = [pair["score"] for pair in cross_pairs + within_pairs if
                              (pair["left_split"], pair["left_id"]) == key or
                              (pair["right_split"], pair["right_id"]) == key]
            writer.writerow({
                "cluster": component_by_record[key], "split": split, "id": record_id,
                "scenario_family": row["scenario_family"],
                "language": row["quality_contracts"][0].get("response_language"),
                "max_cross_split_similarity": max(related_scores),
                "user_prompt": next(message["content"] for message in reversed(row["messages"]) if message["role"] == "user"),
                "assistant_answer": row["messages"][-1]["content"],
                "human_rewrite": "", "human_notes": "",
            })

    split_pair_counts: dict[str, int] = {}
    for pair in cross_pairs:
        name = "-".join(sorted((pair["left_split"], pair["right_split"])))
        split_pair_counts[name] = split_pair_counts.get(name, 0) + 1
    summary = {
        "threshold": args.threshold,
        "cross_split_pair_count": len(cross_pairs),
        "within_split_pair_count": len(within_pairs),
        "max_within_split_similarity": max((pair["score"] for pair in within_pairs), default=0.0),
        "max_cross_split_similarity": round(max_cross_split_similarity, 4),
        "impacted_records": len(adjacency),
        "split_pair_counts": split_pair_counts,
        "clusters": [
            {"cluster": index, "size": len(component),
             "records": [{"split": split, "id": record_id} for split, record_id in sorted(component)]}
            for index, component in enumerate(components, 1)
        ],
        "cross_split_gate_passed": not cross_pairs,
        "human_diversity_review_required": bool(within_pairs),
        "note": "Machine audit only; blank rewrite fields require a real author/reviewer.",
    }
    (args.output / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n"
    )
    print(json.dumps(summary | {"clusters": [{"cluster": item["cluster"], "size": item["size"]} for item in summary["clusters"]]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
