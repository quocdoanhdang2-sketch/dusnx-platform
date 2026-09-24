from __future__ import annotations

from pathlib import Path

import pytest
import torch

from dusnx_core.benchmark import (
    BenchmarkStep,
    BenchmarkValidationError,
    evaluate_benchmark,
    read_benchmark,
    validate_benchmark,
)
from dusnx_core.model import DusnxState
from dusnx_core.routing_policy import RouteDecision


FIXTURE = Path(__file__).parent / "fixtures" / "benchmark_v1_fixture.jsonl"
INVALID_FIXTURE = Path(__file__).parent / "fixtures" / "benchmark_v1_invalid_fixture.jsonl"


def make_step(**overrides) -> BenchmarkStep:
    values = {
        "case_id": "case-1",
        "sequence_id": "sequence-1",
        "global_user_id": "user-1",
        "step": 1,
        "platform": "web",
        "content": "test content",
        "known_feedback_value": 0.0,
        "expected_intent": "research",
        "expected_agent": "search_rag",
        "expected_action": "search",
        "category": "test",
        "difficulty": "hard",
        "source": "test_fixture",
        "generated_by_ai": False,
        "notes": "Test only.",
    }
    values.update(overrides)
    return BenchmarkStep(**values)


def state(marker: float) -> DusnxState:
    return DusnxState(
        global_state=torch.tensor([[marker, 0.0]]),
        platform_states=torch.zeros(1, 3, 2),
        task_state=torch.zeros(1, 2),
    )


def test_checked_in_fixture_is_valid_and_explicitly_not_a_benchmark():
    rows = read_benchmark(FIXTURE)
    assert len(rows) == 3
    assert {row.source for row in rows} == {"test_fixture"}
    assert all(row.generated_by_ai for row in rows)
    assert all("not an independent benchmark" in row.notes or row.step > 1 for row in rows)


def test_validator_rejects_schema_sequence_identity_and_authorship_errors():
    with pytest.raises(BenchmarkValidationError, match="at least one step"):
        validate_benchmark([])
    with pytest.raises(BenchmarkValidationError, match="expected_intent|extra_forbidden"):
        read_benchmark(INVALID_FIXTURE)

    rows = [
        make_step(case_id="duplicate", step=1, generated_by_ai=True, source="human_authored"),
        make_step(case_id="duplicate", step=3, global_user_id="other-user"),
    ]
    with pytest.raises(BenchmarkValidationError) as exc:
        validate_benchmark(rows)
    message = str(exc.value)
    assert "duplicate case_id" in message
    assert "AI-generated data cannot use source=human_authored" in message
    assert "mixes global_user_id" in message
    assert "steps must be continuous" in message

    with pytest.raises(ValueError, match="must not be blank"):
        make_step(case_id="   ")
    with pytest.raises(BenchmarkValidationError, match="source=ai_generated requires"):
        validate_benchmark([make_step(source="ai_generated", generated_by_ai=False)])


def test_multistep_feedback_state_isolation_and_rule_impact():
    rows = [
        make_step(case_id="a1", sequence_id="a", global_user_id="ua", step=1, content="plain a1"),
        make_step(
            case_id="a2",
            sequence_id="a",
            global_user_id="ua",
            step=2,
            content="rescue-by-rule",
            known_feedback_value=0.8,
        ),
        make_step(case_id="b1", sequence_id="b", global_user_id="ub", step=1, content="harm-by-rule"),
    ]
    observed = []

    def inference(request):
        previous_marker = request.previous_state.global_state[0] if request.previous_state else None
        observed.append((request.global_user_id, request.feedback_value, previous_marker))
        marker = 1.0 if request.global_user_id == "ua" else 9.0
        intent = "chat" if request.content == "rescue-by-rule" else "research"
        return {
            "intent": intent,
            "selected_agent": "search_rag",
            "next_action": "search",
            "confidence": 0.5,
            "new_state": state(marker),
        }

    def rules(_platform, content):
        if content == "rescue-by-rule":
            return RouteDecision("research", "search_rag", "search", 1.0)
        if content == "harm-by-rule":
            return RouteDecision("chat", "conversation", "reply", 1.0)
        return None

    report = evaluate_benchmark(
        rows,
        inference,
        checkpoint="fixture.pt",
        model_version="fixture-model",
        rule_matcher=rules,
    )

    assert observed == [("ua", 0.0, None), ("ua", 0.8, 1.0), ("ub", 0.0, None)]
    assert report["rule_impact"] == {"rescued": 1, "harmed": 1}
    assert report["checkpoint"] == "fixture.pt"
    assert report["model_version"] == "fixture-model"
    assert report["metrics"]["model"]["intent"]["per_class"]["research"]["support"] == 3
    assert "chat" in report["metrics"]["model"]["intent"]["missing_expected_classes"]
    assert len(report["errors"]["model"]) == 1
    assert len(report["errors"]["after_rule_override"]) == 1
