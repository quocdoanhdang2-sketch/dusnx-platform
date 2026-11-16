#!/usr/bin/env python3
"""Measure retrieval for the focused corpus: hit@k, citation, refusal.

This runs the same retrieval gate and scoring the chat pipeline uses, so the
numbers describe what the RAG side can ground, not a separate toy pipeline.

Cases are assistant-drafted and marked ``pending_human_review``; this script
never upgrades that status.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve()
PYTHON_DIR = HERE.parents[1]
ROOT = HERE.parents[2]
sys.path.insert(0, str(PYTHON_DIR))
sys.path.insert(0, str(PYTHON_DIR / "src"))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from apps.ai_api import rag  # noqa: E402

DEFAULT_DB = ROOT / "runtime" / "domain-rag" / "rag-domain.db"
DEFAULT_CASES = ROOT / "datasets" / "domain_corpus_v1" / "test_set.jsonl"
DEFAULT_REPORT = ROOT / "runtime" / "domain-rag" / "evaluation.json"


def load_cases(path: Path) -> list[dict]:
    cases = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    if not cases:
        raise ValueError("test set is empty")
    return cases


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", default=str(DEFAULT_DB))
    parser.add_argument("--cases", default=str(DEFAULT_CASES))
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument("--report", default=str(DEFAULT_REPORT))
    args = parser.parse_args()

    os.environ["DUSNX_RAG_DB"] = str(Path(args.db).resolve())
    status = rag.index_status()
    if not status.get("available"):
        print(json.dumps({"status": "no_index", **status}, ensure_ascii=False, indent=2))
        return 2

    cases = load_cases(Path(args.cases).resolve())
    details = []
    answer_cases = [case for case in cases if case["expect"] == "answer"]
    refuse_cases = [case for case in cases if case["expect"] == "refuse"]
    hit_at = {1: 0, 3: 0, 5: 0}
    answered = 0
    cited = 0
    scoped_open = 0
    refused = 0

    for case in cases:
        hits = rag.retrieve(case["question"], top_k=args.top_k)
        gate = rag.should_retrieve(case["question"])
        scoped = rag.should_retrieve_scoped(case["question"])
        evidence = rag.has_evidence(hits)
        if hits:
            rag.build_context(hits)
        top_paths = [hit.path for hit in hits]
        record = {
            "id": case["id"],
            "question": case["question"],
            "expect": case["expect"],
            "gate_open": gate,
            "scoped_gate": scoped,
            "has_evidence": evidence,
            "top_paths": top_paths[:3],
        }
        if case["expect"] == "refuse":
            passed = (not scoped) or (not evidence)
            refused += 1 if passed else 0
            record["passed"] = passed
        else:
            scoped_open += 1 if scoped else 0
            expected = set(case["expected_paths"])
            for k in hit_at:
                if expected.intersection(top_paths[:k]):
                    hit_at[k] += 1
            answered += 1 if (scoped and evidence) else 0
            cited += 1 if (hits and hits[0].source_id) else 0
            record["passed"] = bool(expected.intersection(top_paths))
            record["expected_paths"] = sorted(expected)
        details.append(record)

    def rate(numerator: int, denominator: int) -> float | None:
        return round(numerator / denominator, 4) if denominator else None

    summary = {
        "status": "measured",
        "db": status.get("path"),
        "cases": len(cases),
        "cases_sha256": hashlib.sha256(
            Path(args.cases).read_bytes()).hexdigest(),
        "answer": {
            "cases": len(answer_cases),
            "hit_at_1": rate(hit_at[1], len(answer_cases)),
            "hit_at_3": rate(hit_at[3], len(answer_cases)),
            "hit_at_5": rate(hit_at[5], len(answer_cases)),
            "scoped_gate_open": rate(scoped_open, len(answer_cases)),
            "repo_gate_open": rate(
                sum(1 for detail in details if detail["expect"] == "answer" and detail["gate_open"]),
                len(answer_cases)),
            "grounded_or_abstained": rate(answered, len(answer_cases)),
            "citation_present": rate(cited, len(answer_cases)),
        },
        "refuse": {
            "cases": len(refuse_cases),
            "refused": rate(refused, len(refuse_cases)),
        },
        "review_status": "assistant-drafted, pending_human_review",
        "details": details,
    }
    report_path = Path(args.report).resolve()
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
