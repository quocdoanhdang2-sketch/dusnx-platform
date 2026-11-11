"""Regression gate for the offline RAG evaluation harness."""
import pytest

from apps.ai_api import rag
from eval_rag import CASES, NEGATIVE_CASES, evaluate


def test_eval_harness_meets_retrieval_thresholds():
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
