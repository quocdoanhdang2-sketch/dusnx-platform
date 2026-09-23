from __future__ import annotations
from typing import Any
from pydantic import BaseModel, Field


class IngressEvent(BaseModel):
    platform: str
    platform_user_id: str
    content: str = ""
    event_type: str = "message"
    feedback_value: float = 0.0


class CanonicalUserEvent(BaseModel):
    global_user_id: str
    platform: str
    content: str = ""
    event_type: str = "message"
    time_gap_hours: float = 0.0
    feedback_value: float = 0.0


class StateSnapshot(BaseModel):
    global_state: list[float]
    platform_states: list[list[float]]
    task_state: list[float]
    state_version: int = 0


class ProcessRequest(BaseModel):
    global_user_id: str
    platform: str
    content: str
    event_type: str = "message"
    time_gap_hours: float = 0.0
    feedback_value: float = 0.0
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
