"""Conversation pilot contract. Labels are never part of adapter inputs."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .constants import AGENTS, INTENTS, NEXT_ACTIONS

CHAT_INTENTS = set(INTENTS) | {
    "memory_create", "decision_modify_intent", "decision_update", "decision_update_failed",
    "decision_update_cancelled", "awaiting_confirm", "clarify_ambiguous_decision", "clarify_missing_context",
}
CHAT_AGENTS = set(AGENTS) | {"memory"}
CHAT_ACTIONS = set(NEXT_ACTIONS) | {"create_memory", "update_memory", "await_confirm", "no_op"}


class PilotStep(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    case_id: str = Field(min_length=1)  # unique step ID, consistent with benchmark_v1
    sequence_id: str = Field(min_length=1)
    step: int = Field(ge=1)
    platform: Literal["web", "powerpoint", "zalo"]
    user_message: str = Field(min_length=1)
    session_id: str = Field(min_length=1)
    project_id: str | None
    event_type: str
    prior_event_ids: list[str]
    known_feedback_value: float = Field(ge=-1, le=1)
    category: str = Field(min_length=1)
    label_source: Literal["ai_authored_takeover", "human_authored", "test_fixture"]
    review_status: Literal["not_independently_reviewed", "independently_reviewed"]
    reviewer: str | None
    expected_intent: str | None
    expected_agent: str | None
    expected_next_action: str | None
    target_query: bool
    gold_active_facts: list[str]
    gold_obsolete_facts: list[str]
    requires_clarification: bool
    expected_keywords: list[str]
    forbidden_keywords: list[str]

    @model_validator(mode="after")
    def labels(self):
        for name, allowed in (("expected_intent", CHAT_INTENTS), ("expected_agent", CHAT_AGENTS),
                              ("expected_next_action", CHAT_ACTIONS)):
            value = getattr(self, name)
            if value is not None and value not in allowed:
                raise ValueError(f"invalid {name}: {value}")
        if self.review_status == "independently_reviewed" and not self.reviewer:
            raise ValueError("independent review requires a named reviewer")
        for name in ("case_id", "sequence_id", "user_message", "session_id", "category"):
            if not getattr(self, name).strip():
                raise ValueError(f"blank {name}")
        return self

    def prediction_input(self) -> dict:
        # Explicit allowlist: no gold, target_query, review metadata or future feedback.
        return self.model_dump(include={"step", "platform", "user_message", "session_id",
                                        "project_id", "event_type", "known_feedback_value"})


def read_pilot(path: str | Path) -> list[PilotStep]:
    rows = []
    seen = set()
    sequences: dict[str, list[str]] = {}
    for line_no, line in enumerate(Path(path).read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            row = PilotStep.model_validate(json.loads(line))
            if row.case_id in seen:
                raise ValueError(f"duplicate case_id {row.case_id}")
            prior = sequences.setdefault(row.sequence_id, [])
            if row.step != len(prior) + 1:
                raise ValueError("sequence steps must appear in order, continuous from 1")
            if row.prior_event_ids != prior:
                raise ValueError("prior_event_ids must reference only preceding events in this sequence")
            if row.known_feedback_value != 0:
                raise ValueError("pilot has no observed feedback; known_feedback_value must be zero")
            seen.add(row.case_id)
            prior.append(row.case_id)
            rows.append(row)
        except ValueError as exc:
            raise ValueError(f"line {line_no}: {exc}") from exc
    if not rows:
        raise ValueError("empty pilot")
    return rows
