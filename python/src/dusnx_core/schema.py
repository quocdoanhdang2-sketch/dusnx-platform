from __future__ import annotations
from typing import Any
from pydantic import BaseModel, Field


STATE_SCHEMA_VERSION = 2


class IngressEvent(BaseModel):
    platform: str
    platform_user_id: str
    content: str = ""
    event_type: str = "message"
    feedback_value: float = Field(
        default=0.0,
        description="Feedback from the previous event, known before this event is processed.",
    )


class CanonicalUserEvent(BaseModel):
    global_user_id: str
    platform: str
    content: str = ""
    event_type: str = "message"
    time_gap_hours: float = 0.0
    feedback_value: float = Field(
        default=0.0,
        description="Feedback from the previous event, known before this event is processed.",
    )


class StateSnapshot(BaseModel):
    global_state: list[float]
    platform_states: list[list[float]]
    task_state: list[float]
    # Counts state updates only; it is not a compatibility version.
    state_version: int = 0
    # Compatibility metadata. None is deliberately retained for legacy states
    # so the service can reset them explicitly rather than guessing.
    state_schema_version: int | None = None
    model_version: str | None = None


class ProcessRequest(BaseModel):
    global_user_id: str
    platform: str
    content: str
    event_type: str = "message"
    time_gap_hours: float = 0.0
    feedback_value: float = Field(
        default=0.0,
        description="Feedback from the previous event, known before this event is processed.",
    )
    previous_state: StateSnapshot | None = None


class ProcessResponse(BaseModel):
    global_user_id: str
    intent: str
    selected_agent: str
    next_action: str
    confidence: float
    state_snapshot: StateSnapshot
    runtime_mode: str = "trained_dusnx"
    routing_source: str = "model"
    agent_output: dict[str, Any] = Field(default_factory=dict)
    state_reset: bool = False
    reset_reason: str | None = None
