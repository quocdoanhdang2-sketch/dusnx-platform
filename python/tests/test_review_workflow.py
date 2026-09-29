"""Unit tests for blind review package, validation, gold comparison, and adjudication workflow."""
import json
from pathlib import Path
import pytest

from dusnx_core.data_pipeline import read_rows, write_rows
from dusnx_core.review import (
    review_sample, validate_review, agreement, adjudicate,
    normalize_gold_benchmark, is_blind_template, FIELDS
)

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_blind_template_has_no_gold_leaks():
    """Verify blind template strictly hides all gold labels, predictions, and keywords."""
    gold_rows = read_rows(REPO_ROOT / "benchmarks/holdout_v2.jsonl")
    blind = review_sample(gold_rows)
    assert len(blind) == len(gold_rows)

    LEAK_FIELDS = {
        "expected_intent", "expected_agent", "expected_next_action",
        "gold_active_facts", "gold_obsolete_facts", "expected_keywords",
        "forbidden_keywords", "model_prediction", "predictions",
    }

    for row in blind:
        for leak in LEAK_FIELDS:
            assert leak not in row, f"Blind row leaked field {leak}!"
        assert row["reviewer"] is None
        assert row["review_date"] is None
        labels = row["labels"]
        for f in FIELDS:
            assert labels[f] is None, f"Blind row has non-null label for {f}: {labels[f]}"
        assert is_blind_template([row]) is True


def test_blind_template_rejected_in_validation_and_agreement():
    """Verify unlabelled blind templates cannot be passed as reviewed files or compared."""
    gold_rows = read_rows(REPO_ROOT / "benchmarks/holdout_v2.jsonl")
    blind = review_sample(gold_rows)

    with pytest.raises(ValueError, match="unlabelled blind review template"):
        validate_review(blind)

    with pytest.raises(ValueError, match="Cannot compute agreement against an unlabelled blind template"):
        agreement(blind, blind)


def test_gold_normalization():
    """Verify normalize_gold_benchmark extracts expected labels into review schema."""
    gold_rows = read_rows(REPO_ROOT / "benchmarks/holdout_v2.jsonl")
    norm = normalize_gold_benchmark(gold_rows, reviewer_tag="gold_benchmark_lock")
    assert len(norm) == len(gold_rows)
    for r in norm:
        assert r["reviewer"] == "gold_benchmark_lock"
        assert r["labels"]["intent"] is not None
        assert r["labels"]["agent"] is not None
        assert r["labels"]["action"] is not None
        assert isinstance(r["labels"]["requires_clarification"], bool)


def test_reviewer_vs_gold_agreement_and_adjudication(tmp_path):
    """Verify agreement calculation with Cohen's kappa and adjudication using test_only reviewer."""
    gold_rows = read_rows(REPO_ROOT / "benchmarks/holdout_v2.jsonl")
    norm_gold = normalize_gold_benchmark(gold_rows)

    # Simulate Reviewer A (marked test_only) with 2 intentional disagreements
    rev_a = []
    for i, r in enumerate(norm_gold):
        item = {
            "record_id": r["record_id"],
            "sequence_id": r["sequence_id"],
            "step": r["step"],
            "user_message": r["user_message"],
            "platform": r["platform"],
            "session_id": r["session_id"],
            "source": r["source"],
            "reviewer": "test_only_reviewer_alpha",
            "review_date": "2026-09-29T18:00:00Z",
            "labels": dict(r["labels"]),
            "notes": "simulated test review",
        }
        if i == 0:
            # Introduce a disagreement on intent
            item["labels"]["intent"] = "chat"
        rev_a.append(item)

    # Validate review
    assert validate_review(rev_a) == len(gold_rows)

    # Agreement against gold
    rep = agreement(rev_a, norm_gold)
    assert rep["records"] == len(gold_rows)
    assert len(rep["disagreements"]) == 1
    assert rep["disagreements"][0]["field"] == "intent"
    assert rep["fields"]["agent"]["agreement_rate"] == 1.0
    assert rep["fields"]["intent"]["disagreements_count"] == 1

    # Adjudication
    adj = adjudicate(
        rev_a, norm_gold,
        adjudicator="test_only_lead_adjudicator",
        resolved_labels={rev_a[0]["record_id"]: {"intent": "memory_create"}}
    )
    assert adj["status"] == "test_only_synthetic_adjudication"
    assert adj["adjudicator"] == "test_only_lead_adjudicator"
    assert adj["disagreements_count"] == 1
    # Check that resolution was applied
    rec0 = adj["records"][0]
    assert rec0["labels"]["intent"] == "memory_create"
    assert rec0["resolutions"]["intent"] == "Manual resolution"
