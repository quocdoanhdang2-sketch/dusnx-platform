"""Offline RAG retrieval evaluation harness.

Runs a fixed, repository-derived query set against the local FTS5 index and
reports hit@1, hit@k, MRR and retrieval-gate accuracy. No model call, no user
data, no network: a deterministic regression gate for retrieval quality.

Usage:
    python scripts/eval_rag.py [--top-k 5] [--json runtime/rag-eval.json]

Exit code 1 when hit@k, MRR or gate accuracy fall below the thresholds, so CI
or a local pre-commit step can fail on a retrieval regression.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "python") not in sys.path:
    sys.path.insert(0, str(ROOT / "python"))

from apps.ai_api import rag  # noqa: E402

REPORT_PATH = ROOT / "docs" / "reports" / "DUSN-X_BAO_CAO_TONG_THE_20261107.html"

# Acceptable source files per query. Multiple paths are allowed because both
# canonical documentation and the consolidated report answer these questions.
CASES = [
    {"query": "DUSN-X là gì?",
     "accept": ("docs/ARCHITECTURE.md", "README.md", str(REPORT_PATH.relative_to(ROOT)).replace("\\", "/"))},
    {"query": "kiến trúc DUSN-X gồm những tầng nào?",
     "accept": ("docs/ARCHITECTURE.md", "docs/GITHUB_VA_MO_RONG.md",
                "docs/reports/DUSN-X_BAO_CAO_TONG_THE_20261107.html")},
    {"query": "cấu hình Ollama provider",
     "accept": ("python/apps/ai_api/provider.py", "docs/OPERATIONS_RELIABILITY.md",
                "docs/reports/DUSN-X_BAO_CAO_TONG_THE_20261107.html")},
    {"query": "timeout provider là bao nhiêu?",
     "accept": ("python/apps/ai_api/provider.py", "docs/OPERATIONS_RELIABILITY.md",
                "docs/reports/DUSN-X_BAO_CAO_TONG_THE_20261107.html")},
    {"query": "scrypt password hash", "accept": ("python/apps/ai_api/auth.py",)},
    {"query": "mật khẩu được hash bằng gì?",
     "accept": ("python/apps/ai_api/auth.py", "docs/OPERATIONS_RELIABILITY.md",
                "docs/reports/DUSN-X_BAO_CAO_TONG_THE_20261107.html")},
    {"query": "memory.db chat_messages schema", "accept": ("python/apps/ai_api/memory.py",)},
    {"query": "trí nhớ của chatbot lưu ở đâu?",
     "accept": ("python/apps/ai_api/memory.py", "docs/CHAT_RESPONSE_CONTRACT.md",
                "docs/reports/DUSN-X_BAO_CAO_TONG_THE_20261107.html")},
    {"query": "ProxyToAiApi gateway proxy",
     "accept": ("gateway-dotnet/Program.cs", "docs/ARCHITECTURE.md",
                "docs/reports/DUSN-X_BAO_CAO_TONG_THE_20261107.html")},
    {"query": "word-taskpane validateProposal",
     "accept": ("word-addin/word-taskpane.js", "docs/WORD_ADDIN_RUNBOOK.md",
                "docs/reports/DUSN-X_BAO_CAO_TONG_THE_20261107.html")},
    {"query": "RAG retrieve FTS5", "accept": ("python/apps/ai_api/rag.py",)},
    {"query": "How does the Word add-in work?",
     "accept": ("docs/WORD_ADDIN_RUNBOOK.md", "docs/reports/DUSN-X_BAO_CAO_TONG_THE_20261107.html",
                "word-addin/word-taskpane.js")},
    {"query": "What does the DUSN-X gateway do?",
     "accept": ("docs/ARCHITECTURE.md", "docs/GUIDE_TUNG_BUOC.md", "gateway-dotnet/Program.cs",
                "docs/reports/DUSN-X_BAO_CAO_TONG_THE_20261107.html")},
    {"query": "kien truc he thong gom nhung tang nao?",
     "accept": ("docs/ARCHITECTURE.md", "docs/reports/DUSN-X_BAO_CAO_TONG_THE_20261107.html")},
    {"query": "mat khau duoc hash bang gi?",
     "accept": ("python/apps/ai_api/auth.py", "docs/reports/DUSN-X_BAO_CAO_TONG_THE_20261107.html")},
    {"query": "answer_from_hits trả về gì?", "accept": ("python/apps/ai_api/rag.py",)},
]

# The corpus covers DUSN-X, not general knowledge. These must not reach the
# retrieval gate, otherwise unrelated passages would enter the prompt.
NEGATIVE_CASES = [
    "hôm nay là ngày bao nhiêu",
    "thời tiết hôm nay thế nào",
    "giá vàng hôm nay",
    "cách nấu phở bò",
]

HIT_AT_K_THRESHOLD = 1.0
MRR_THRESHOLD = 0.75
GATE_ACCURACY_THRESHOLD = 1.0


def _matches(path: str, accept: tuple[str, ...]) -> bool:
    normalized = path.replace("\\", "/")
    return any(normalized == item or normalized.startswith(item.rstrip("/") + "/")
               for item in accept)


def evaluate(top_k: int = 5) -> dict:
    status = rag.index_status()
    if not status.get("available"):
        return {"available": False, "error": "rag_index_unavailable", "index": status}

    results = []
    for case in CASES:
        query = case["query"]
        hits = rag.retrieve(query, top_k=top_k)
        rank = next((position for position, hit in enumerate(hits, 1)
                     if _matches(hit.path, case["accept"])), None)
        answer = rag.answer_from_hits(query, hits, language="vi") if hits else None
        results.append({
            "query": query,
            "gate": rag.should_retrieve(query),
            "evidence": rag.has_evidence(hits),
            "rank": rank,
            "reciprocal_rank": 0.0 if rank is None else round(1.0 / rank, 4),
            "top_hit": hits[0].path if hits else None,
            "hits": [{"rank": position, "path": hit.path, "score": round(hit.score, 2)}
                     for position, hit in enumerate(hits, 1)],
            "extractive_answer": bool(answer),
            "cited_answer": bool(answer and "[S" in answer),
        })

    negatives = []
    for query in NEGATIVE_CASES:
        hits = rag.retrieve(query, top_k=top_k)
        negatives.append({"query": query, "gate": rag.should_retrieve(query),
                          "top_score": round(hits[0].score, 2) if hits else None})

    total = len(results)
    hit_at_1 = sum(1 for item in results if item["rank"] == 1) / total
    hit_at_k = sum(1 for item in results if item["rank"] is not None) / total
    mrr = sum(item["reciprocal_rank"] for item in results) / total
    gate_correct = sum(1 for item in results if item["gate"]) + sum(
        1 for item in negatives if not item["gate"])
    gate_accuracy = gate_correct / (total + len(negatives))
    cited = [item for item in results if item["extractive_answer"]]
    citation_ok = all(item["cited_answer"] for item in cited)

    metrics = {
        "hit_at_1": round(hit_at_1, 4),
        "hit_at_k": round(hit_at_k, 4),
        "mrr": round(mrr, 4),
        "gate_accuracy": round(gate_accuracy, 4),
        "extractive_answers": len(cited),
        "citation_ok": citation_ok,
        "cases": total,
        "negative_cases": len(negatives),
    }
    passed = (hit_at_k >= HIT_AT_K_THRESHOLD and mrr >= MRR_THRESHOLD
              and gate_accuracy >= GATE_ACCURACY_THRESHOLD and citation_ok)
    return {"available": True, "checked_at": datetime.now(timezone.utc).isoformat(),
            "index": status, "top_k": top_k, "metrics": metrics,
            "cases": results, "negatives": negatives, "passed": passed}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument("--json", type=Path, default=None)
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args(argv)

    report = evaluate(top_k=max(1, args.top_k))
    if not report.get("available"):
        print(f"RAG index unavailable: {report.get('index')}")
        return 1

    if not args.quiet:
        print(f"Index: {report['index']['path']} "
              f"({report['index']['documents']} docs / {report['index']['chunks']} chunks)")
        for item in report["cases"]:
            rank = item["rank"] if item["rank"] is not None else "MISS"
            print(f"  rank={rank!s:<4} gate={str(item['gate']):<5} {item['query']}")
        for item in report["negatives"]:
            print(f"  gate={str(item['gate']):<5} (off-topic) {item['query']}")
        print("\nMetrics: " + json.dumps(report["metrics"], ensure_ascii=False))

    if args.json:
        output = args.json if args.json.is_absolute() else ROOT / args.json
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"Report: {output}")

    print("PASS" if report["passed"] else "FAIL")
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
