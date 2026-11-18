"""Regression gate for the offline RAG evaluation harness."""
from pathlib import Path

import pytest

from apps.ai_api import rag
from eval_rag import CASES, NEGATIVE_CASES, evaluate

# These cases describe DUSN-X repository content. Pin the harness to the
# repository index explicitly: rag.database_path() now prefers the club index
# when present, which would silently change what this gate measures.
REPO_INDEX = Path(__file__).resolve().parents[2] / "python" / "data" / "rag.db"


def test_eval_harness_meets_retrieval_thresholds(monkeypatch):
    if not REPO_INDEX.is_file():
        pytest.skip("Repository RAG index not built in this workspace")
    monkeypatch.setenv("DUSNX_RAG_DB", str(REPO_INDEX))
    if not rag.is_available():
        pytest.skip("RAG index not built in this workspace")
    report = evaluate(top_k=5)
    assert report["available"] is True
    metrics = report["metrics"]
    assert metrics["hit_at_k"] == 1.0
    assert metrics["mrr"] >= 0.75
    assert metrics["gate_accuracy"] == 1.0
    assert metrics["citation_ok"] is True
    assert len(report["cases"]) == len(CASES)
    assert [item["query"] for item in report["negatives"]] == NEGATIVE_CASES
