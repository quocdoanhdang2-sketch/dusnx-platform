from __future__ import annotations

import hashlib
import math
import os
import re
from pathlib import Path

import torch
from fastapi import FastAPI, HTTPException

from dusnx_core.checkpoint import load_checkpoint
from dusnx_core.config import ModelConfig
from dusnx_core.constants import PLATFORMS
from dusnx_core.inference import process_one, state_to_snapshot
from dusnx_core.schema import ProcessRequest, ProcessResponse, StateSnapshot

app = FastAPI(title="DUSN-X AI API", version="0.2.0")

CHECKPOINT = os.getenv("DUSNX_CHECKPOINT", "/app/artifacts/dusnx_smoke.pt")
DEVICE = "cuda" if torch.cuda.is_available() and os.getenv("DUSNX_DEVICE", "auto") != "cpu" else "cpu"
MODEL = None
CFG: ModelConfig | None = None
META: dict = {}
RUNTIME_MODE = "bootstrap_rules"


def load_model_once() -> None:
    """Load a trained checkpoint, or keep a deterministic bootstrap mode for first run."""
    global MODEL, CFG, META, RUNTIME_MODE
    if MODEL is not None:
        return

    path = Path(CHECKPOINT)
    if not path.exists():
        CFG = ModelConfig()
        META = {
            "mode": "bootstrap_rules",
            "warning": "No checkpoint loaded. Train configs/smoke.yaml to enable DUSN-X inference.",
        }
        RUNTIME_MODE = "bootstrap_rules"
        return

    MODEL, CFG, META = load_checkpoint(path, DEVICE)
    RUNTIME_MODE = "trained_dusnx"


@app.on_event("startup")
def startup() -> None:
    load_model_once()


@app.get("/health")
def health():
    return {
        "status": "ok",
        "device": DEVICE,
        "runtime_mode": RUNTIME_MODE,
        "checkpoint": CHECKPOINT,
        "metadata": META,
    }


def detect_route(content: str) -> tuple[str, str, str, float]:
    text = content.casefold()
    if any(word in text for word in ("slide", "powerpoint", "trình chiếu", "speaker note")):
        return "presentation_edit", "productivity", "edit_slide", 0.82
    if any(word in text for word in ("tóm tắt", "rút gọn", "ý chính", "summarize")):
        return "summarize", "productivity", "summarize", 0.79
    if any(word in text for word in ("tìm", "nghiên cứu", "phân tích", "research", "search")):
        return "research", "search_rag", "search", 0.77
    if any(word in text for word in ("tiếp tục", "làm tiếp", "hôm trước", "continue")):
        return "followup", "conversation", "clarify", 0.72
    if any(word in text for word in ("gợi ý", "đề xuất", "recommend")):
        return "recommendation", "conversation", "recommend", 0.74
    return "chat", "conversation", "reply", 0.64


def initial_bootstrap_state() -> StateSnapshot:
    cfg = CFG or ModelConfig()
    return StateSnapshot(
        global_state=[0.0] * cfg.global_state_dim,
        platform_states=[[0.0] * cfg.platform_state_dim for _ in PLATFORMS],
        task_state=[0.0] * cfg.task_state_dim,
        state_version=0,
    )


def bootstrap_state_update(req: ProcessRequest, intent: str) -> StateSnapshot:
    previous = req.previous_state or initial_bootstrap_state()
    decay = math.exp(-0.015 * max(0.0, req.time_gap_hours))
    global_state = [value * decay for value in previous.global_state]
    platform_states = [row[:] for row in previous.platform_states]
    task_state = [value * decay for value in previous.task_state]

    words = re.findall(r"\w+", req.content.casefold(), flags=re.UNICODE) or [req.content]
    for word in words:
        digest = hashlib.sha256(word.encode("utf-8")).digest()
        index = int.from_bytes(digest[:4], "big") % len(global_state)
        signal = 0.04 + (digest[4] / 255.0) * 0.06
        global_state[index] = max(-1.0, min(1.0, global_state[index] + signal))

    platform_index = PLATFORMS.index(req.platform)
    platform_row = platform_states[platform_index]
    for i in range(min(8, len(platform_row))):
        platform_row[i] = max(-1.0, min(1.0, platform_row[i] * decay + 0.04))

    intent_index = ["chat", "research", "summarize", "presentation_edit", "recommendation", "followup"].index(intent)
    task_state[intent_index % len(task_state)] = max(
        -1.0,
        min(1.0, task_state[intent_index % len(task_state)] + 0.15 + 0.05 * req.feedback_value),
    )

    return StateSnapshot(
        global_state=global_state,
        platform_states=platform_states,
        task_state=task_state,
        state_version=previous.state_version + 1,
    )


def requested_slide_count(content: str) -> int:
    match = re.search(r"(?:create|tạo)\s+(\d{1,2})\s+slide", content.casefold())
    if not match:
        return 5
    return max(1, min(20, int(match.group(1))))


def build_slide_outline(content: str) -> list[dict]:
    count = requested_slide_count(content)
    topic = re.sub(r"^(?:create|tạo)\s+\d{1,2}\s+slides?\.?\s*", "", content, flags=re.I).strip()
    topic = topic or "DUSN-X"
    slides = []
    for index in range(1, count + 1):
        slides.append(
            {
                "index": index,
                "title": f"{topic} — phần {index}",
                "bullets": [
                    f"Mục tiêu của phần {index}",
                    "Luận điểm hoặc dữ liệu cần trình bày",
                    "Kết nối với trạng thái người dùng DUSN-X",
                ],
            }
        )
    return slides


def execute_demo_agent(agent: str, req: ProcessRequest, intent: str, next_action: str):
    if agent == "search_rag":
        return {
            "type": "search_plan",
            "message": "Search/RAG Agent selected. Retriever connection is a Phase 2 task.",
            "query": req.content,
            "planned_queries": [req.content, f"Tổng quan {req.content}", f"Ứng dụng {req.content}"],
        }
    if agent == "productivity":
        output = {
            "type": "productivity_plan",
            "message": "Productivity Agent selected for Web/PowerPoint workflow.",
            "action": next_action,
            "source_text": req.content,
        }
        if intent == "presentation_edit":
            output["slides"] = build_slide_outline(req.content)
        return output
    return {
        "type": "conversation",
        "message": f"Conversation Agent selected. Predicted intent: {intent}.",
        "echo": req.content,
    }


@app.post("/v1/process", response_model=ProcessResponse)
def process(req: ProcessRequest):
    if req.platform not in PLATFORMS:
        raise HTTPException(status_code=400, detail=f"platform must be one of {PLATFORMS}")

    if MODEL is None:
        intent, agent, next_action, confidence = detect_route(req.content)
        snapshot = bootstrap_state_update(req, intent)
    else:
        result = process_one(MODEL, CFG, req, DEVICE)
        intent = result["intent"]
        agent = result["selected_agent"]
        next_action = result["next_action"]
        confidence = result["confidence"]
        version = (req.previous_state.state_version if req.previous_state else 0) + 1
        snapshot = StateSnapshot(**state_to_snapshot(result["new_state"], version))

    return ProcessResponse(
        global_user_id=req.global_user_id,
        intent=intent,
        selected_agent=agent,
        next_action=next_action,
        confidence=confidence,
        state_snapshot=snapshot,
        runtime_mode=RUNTIME_MODE,
        agent_output=execute_demo_agent(agent, req, intent, next_action),
    )
