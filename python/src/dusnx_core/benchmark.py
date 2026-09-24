from __future__ import annotations

import csv
import json
from collections import defaultdict
from pathlib import Path
from typing import Any, Callable, Iterable

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator
from sklearn.metrics import confusion_matrix, precision_recall_fscore_support

from .constants import AGENTS, INTENTS, NEXT_ACTIONS, PLATFORMS
from .inference import state_to_snapshot
from .routing_policy import RouteDecision, match_explicit_route
from .schema import STATE_SCHEMA_VERSION, ProcessRequest, StateSnapshot


DIFFICULTIES = {"easy", "medium", "hard"}
SOURCES = {"human_authored", "ai_generated", "test_fixture"}


class BenchmarkStep(BaseModel):
    """One pre-labelled event. Feedback at step t was observed before step t."""

    model_config = ConfigDict(extra="forbid")

    case_id: str = Field(min_length=1)
    sequence_id: str = Field(min_length=1)
    global_user_id: str = Field(min_length=1)
    step: int = Field(ge=1)
    platform: str
    content: str = Field(min_length=1)
    known_feedback_value: float = Field(ge=-1.0, le=1.0)
    expected_intent: str
    expected_agent: str
    expected_action: str
    category: str = Field(min_length=1)
    difficulty: str
    source: str
    generated_by_ai: bool
    notes: str

    @field_validator("case_id", "sequence_id", "global_user_id", "content", "category")
    @classmethod
    def non_blank_text(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("must not be blank")
        return value

    @field_validator("platform")
    @classmethod
    def valid_platform(cls, value: str) -> str:
        if value not in PLATFORMS:
            raise ValueError(f"must be one of {PLATFORMS}")
        return value

    @field_validator("expected_intent")
    @classmethod
    def valid_intent(cls, value: str) -> str:
        if value not in INTENTS:
            raise ValueError(f"must be one of {INTENTS}")
        return value

    @field_validator("expected_agent")
    @classmethod
    def valid_agent(cls, value: str) -> str:
        if value not in AGENTS:
            raise ValueError(f"must be one of {AGENTS}")
        return value

    @field_validator("expected_action")
    @classmethod
    def valid_action(cls, value: str) -> str:
        if value not in NEXT_ACTIONS:
            raise ValueError(f"must be one of {NEXT_ACTIONS}")
        return value

    @field_validator("difficulty")
    @classmethod
    def valid_difficulty(cls, value: str) -> str:
        if value not in DIFFICULTIES:
            raise ValueError(f"must be one of {sorted(DIFFICULTIES)}")
        return value

    @field_validator("source")
    @classmethod
    def valid_source(cls, value: str) -> str:
        if value not in SOURCES:
            raise ValueError(f"must be one of {sorted(SOURCES)}")
        return value


class BenchmarkValidationError(ValueError):
    pass


def read_benchmark(path: str | Path) -> list[BenchmarkStep]:
    parsed: list[BenchmarkStep] = []
    errors: list[str] = []
    with Path(path).open(encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            try:
                parsed.append(BenchmarkStep.model_validate_json(line))
            except (ValidationError, ValueError) as exc:
                errors.append(f"line {line_number}: {exc}")
    if errors:
        raise BenchmarkValidationError("Invalid benchmark JSONL:\n" + "\n".join(errors))
    validate_benchmark(parsed)
    return parsed


def validate_benchmark(steps: Iterable[BenchmarkStep]) -> list[BenchmarkStep]:
    rows = list(steps)
    errors: list[str] = []
    if not rows:
        errors.append("benchmark must contain at least one step")
    seen_case_ids: set[str] = set()
    grouped: dict[str, list[BenchmarkStep]] = defaultdict(list)

    for row in rows:
        if row.case_id in seen_case_ids:
            errors.append(f"duplicate case_id: {row.case_id}")
        seen_case_ids.add(row.case_id)
        if row.generated_by_ai and row.source == "human_authored":
            errors.append(f"{row.case_id}: AI-generated data cannot use source=human_authored")
        if row.source == "ai_generated" and not row.generated_by_ai:
            errors.append(f"{row.case_id}: source=ai_generated requires generated_by_ai=true")
        grouped[row.sequence_id].append(row)

    for sequence_id, sequence in grouped.items():
        users = {row.global_user_id for row in sequence}
        if len(users) != 1:
            errors.append(f"sequence {sequence_id} mixes global_user_id values: {sorted(users)}")
        ordered = sorted(sequence, key=lambda row: row.step)
        actual_steps = [row.step for row in ordered]
        expected_steps = list(range(1, len(ordered) + 1))
        if actual_steps != expected_steps:
            errors.append(f"sequence {sequence_id} steps must be continuous from 1; got {actual_steps}")
        if ordered and ordered[0].known_feedback_value != 0.0:
            errors.append(f"sequence {sequence_id} step 1 known_feedback_value must be 0.0")

    if errors:
        raise BenchmarkValidationError("Invalid benchmark:\n" + "\n".join(errors))
    return sorted(rows, key=lambda row: (row.sequence_id, row.step))


InferenceFn = Callable[[ProcessRequest], dict[str, Any]]
RuleFn = Callable[[str, str], RouteDecision | None]


def _classification(expected: list[str], predicted: list[str], labels: list[str]) -> dict[str, Any]:
    precision, recall, f1, support = precision_recall_fscore_support(
        expected, predicted, labels=labels, zero_division=0
    )
    per_class = {
        label: {
            "precision": float(precision[index]),
            "recall": float(recall[index]),
            "f1": float(f1[index]),
            "support": int(support[index]),
        }
        for index, label in enumerate(labels)
    }
    class_f1 = [entry["f1"] for entry in per_class.values()]
    present_class_f1 = [entry["f1"] for entry in per_class.values() if entry["support"] > 0]
    missing_classes = [label for label, entry in per_class.items() if entry["support"] == 0]
    return {
        "macro_f1_all_classes": sum(class_f1) / len(class_f1) if class_f1 else 0.0,
        "macro_f1_present_classes": (
            sum(present_class_f1) / len(present_class_f1) if present_class_f1 else 0.0
        ),
        "missing_expected_classes": missing_classes,
        "per_class": per_class,
    }


def evaluate_benchmark(
    steps: Iterable[BenchmarkStep],
    inference: InferenceFn,
    *,
    checkpoint: str,
    model_version: str,
    rule_matcher: RuleFn = match_explicit_route,
) -> dict[str, Any]:
    rows = validate_benchmark(steps)
    states: dict[str, StateSnapshot] = {}
    predictions: list[dict[str, Any]] = []
    rule_rescued = 0
    rule_harmed = 0

    for row in rows:
        previous_state = states.get(row.sequence_id)
        request = ProcessRequest(
            global_user_id=row.global_user_id,
            platform=row.platform,
            content=row.content,
            feedback_value=row.known_feedback_value,
            previous_state=previous_state,
        )
        raw = inference(request)
        version = (previous_state.state_version if previous_state else 0) + 1
        states[row.sequence_id] = StateSnapshot(
            **state_to_snapshot(raw["new_state"], version, STATE_SCHEMA_VERSION, model_version)
        )
        model_prediction = {
            "intent": raw["intent"],
            "agent": raw["selected_agent"],
            "action": raw["next_action"],
        }
        rule = rule_matcher(row.platform, row.content)
        final_prediction = dict(model_prediction)
        if rule is not None:
            final_prediction = {"intent": rule.intent, "agent": rule.agent, "action": rule.next_action}

        expected_route = {
            "intent": row.expected_intent,
            "agent": row.expected_agent,
            "action": row.expected_action,
        }
        model_correct = model_prediction == expected_route
        final_correct = final_prediction == expected_route
        if not model_correct and final_correct:
            rule_rescued += 1
        elif model_correct and not final_correct:
            rule_harmed += 1

        predictions.append({
            **row.model_dump(),
            "model_prediction": model_prediction,
            "final_prediction": final_prediction,
            "rule_applied": rule is not None,
            "confidence": float(raw.get("confidence", 0.0)),
            "model_correct": model_correct,
            "final_correct": final_correct,
        })

    expected_intent = [row.expected_intent for row in rows]
    model_intent = [row["model_prediction"]["intent"] for row in predictions]
    final_intent = [row["final_prediction"]["intent"] for row in predictions]
    expected_agent = [row.expected_agent for row in rows]
    model_agent = [row["model_prediction"]["agent"] for row in predictions]
    final_agent = [row["final_prediction"]["agent"] for row in predictions]
    expected_action = [row.expected_action for row in rows]
    model_action = [row["model_prediction"]["action"] for row in predictions]
    final_action = [row["final_prediction"]["action"] for row in predictions]
    matrix_model = confusion_matrix(expected_intent, model_intent, labels=INTENTS).tolist()
    matrix_final = confusion_matrix(expected_intent, final_intent, labels=INTENTS).tolist()
    return {
        "benchmark_contract": "benchmark_v1",
        "checkpoint": checkpoint,
        "model_version": model_version,
        "case_count": len(rows),
        "sequence_count": len({row.sequence_id for row in rows}),
        "metrics": {
            "model": {
                "intent": _classification(expected_intent, model_intent, INTENTS),
                "agent": _classification(expected_agent, model_agent, AGENTS),
                "action": _classification(expected_action, model_action, NEXT_ACTIONS),
            },
            "after_rule_override": {
                "intent": _classification(expected_intent, final_intent, INTENTS),
                "agent": _classification(expected_agent, final_agent, AGENTS),
                "action": _classification(expected_action, final_action, NEXT_ACTIONS),
            },
        },
        "confusion_matrix": {
            "labels": INTENTS,
            "model": matrix_model,
            "after_rule_override": matrix_final,
        },
        "rule_impact": {"rescued": rule_rescued, "harmed": rule_harmed},
        "errors": {
            "model": [row for row in predictions if not row["model_correct"]],
            "after_rule_override": [row for row in predictions if not row["final_correct"]],
        },
        "predictions": predictions,
    }


def write_report(report: dict[str, Any], output_dir: str | Path) -> None:
    destination = Path(output_dir)
    destination.mkdir(parents=True, exist_ok=True)
    (destination / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    (destination / "errors.json").write_text(
        json.dumps(report["errors"], ensure_ascii=False, indent=2), encoding="utf-8"
    )
    labels = report["confusion_matrix"]["labels"]
    for key in ("model", "after_rule_override"):
        with (destination / f"confusion_matrix_{key}.csv").open("w", encoding="utf-8", newline="") as handle:
            writer = csv.writer(handle)
            writer.writerow(["expected\\predicted", *labels])
            for label, values in zip(labels, report["confusion_matrix"][key], strict=True):
                writer.writerow([label, *values])
