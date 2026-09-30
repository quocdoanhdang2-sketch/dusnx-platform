from __future__ import annotations

import hashlib
import math
import os
import re
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated, Optional

import torch
from fastapi import Depends, FastAPI, HTTPException, Header, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from dusnx_core.checkpoint import load_checkpoint, model_identifier
from dusnx_core.config import ModelConfig
from dusnx_core.constants import PLATFORMS
from dusnx_core.inference import process_one, state_reset_reason, state_to_snapshot
from dusnx_core.routing_policy import match_explicit_route
from dusnx_core.schema import STATE_SCHEMA_VERSION, ProcessRequest, ProcessResponse, StateSnapshot

from .auth import get_auth_db
from .memory import get_memory_db
from .provider import generate_response, get_provider_health
from .llm_evaluation import EvaluationRequest, evaluate as evaluate_llm
from .grounding import memory_answer_with_selection, select_memories
from .decision_updater import (
    find_best_matching_decision,
    synthesize_full_decision,
    extract_modify_components,
)

# ── Model loading ─────────────────────────────────────────────────────────────
SOURCE_ROOT = Path(__file__).resolve().parents[2]
ARTIFACT_ROOT = SOURCE_ROOT.parent if SOURCE_ROOT.name == "python" else SOURCE_ROOT

def resolve_default_checkpoint() -> str:
    env_ckpt = os.getenv("DUSNX_CHECKPOINT")
    if env_ckpt:
        return env_ckpt
    candidates = [
        ARTIFACT_ROOT / "training-results" / "colab-run-01" / "extracted" / "dusnx-router-full-01" / "router.pt",
        ARTIFACT_ROOT / "artifacts" / "dusnx_smoke_v2.pt",
        ARTIFACT_ROOT / "artifacts" / "router_local_v1.pt",
    ]
    for cand in candidates:
        if cand.is_file():
            return str(cand)
    return str(ARTIFACT_ROOT / "artifacts" / "dusnx_smoke_v2.pt")

CHECKPOINT = resolve_default_checkpoint()
DEVICE = "cuda" if torch.cuda.is_available() and os.getenv("DUSNX_DEVICE", "auto") != "cpu" else "cpu"
MODEL = None
CFG: ModelConfig | None = None
META: dict = {}
RUNTIME_MODE = "bootstrap_rules"
MODEL_VERSION = model_identifier(CHECKPOINT, ModelConfig(), RUNTIME_MODE)
LOADED_CHECKPOINT: str | None = None


def load_model(checkpoint_path: str | Path | None = None) -> None:
    """Load model checkpoint with validation. Falls back to bootstrap_rules if missing or incompatible."""
    global MODEL, CFG, META, RUNTIME_MODE, MODEL_VERSION, LOADED_CHECKPOINT, CHECKPOINT
    if checkpoint_path is not None:
        CHECKPOINT = str(checkpoint_path)
    else:
        CHECKPOINT = resolve_default_checkpoint()

    path = Path(CHECKPOINT)
    if not path.is_file():
        missing_path = path.resolve()
        MODEL = None
        CFG = ModelConfig()
        META = {
            "mode": "bootstrap_rules",
            "warning": (
                f"Checkpoint not found: {missing_path}. Specify DUSNX_CHECKPOINT or train a model."
            ),
        }
        RUNTIME_MODE = "bootstrap_rules"
        MODEL_VERSION = model_identifier(CHECKPOINT, CFG, RUNTIME_MODE)
        LOADED_CHECKPOINT = None
        return

    try:
        loaded_model, loaded_cfg, loaded_meta = load_checkpoint(path, DEVICE, validate=True)
        MODEL = loaded_model
        CFG = loaded_cfg
        META = loaded_meta
        RUNTIME_MODE = "trained_dusnx"
        MODEL_VERSION = model_identifier(CHECKPOINT, CFG, RUNTIME_MODE)
        LOADED_CHECKPOINT = str(path.resolve())
    except Exception as e:
        MODEL = None
        CFG = ModelConfig()
        META = {
            "mode": "bootstrap_rules",
            "warning": f"Checkpoint loading failed ({type(e).__name__}): {e}",
        }
        RUNTIME_MODE = "bootstrap_rules"
        MODEL_VERSION = model_identifier(CHECKPOINT, CFG, RUNTIME_MODE)
        LOADED_CHECKPOINT = None


def load_model_once() -> None:
    if MODEL is None and LOADED_CHECKPOINT is None:
        load_model()


def startup() -> None:
    load_model_once()
    # Pre-warm DBs
    get_auth_db()
    get_memory_db()


@asynccontextmanager
async def lifespan(app: FastAPI):
    startup()
    yield


app = FastAPI(title="DUSN-X AI API", version="0.3.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Auth dependency ────────────────────────────────────────────────────────────

def _get_current_user(authorization: Annotated[Optional[str], Header()] = None) -> dict:
    """Extract and verify Bearer token from Authorization header."""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid Authorization header")
    token = authorization[7:]
    user = get_auth_db().verify_token(token)
    if user is None:
        raise HTTPException(status_code=401, detail="Token không hợp lệ hoặc đã hết hạn")
    return user


CurrentUser = Annotated[dict, Depends(_get_current_user)]

@app.post('/v1/llm-evaluation')
def llm_evaluation(req: EvaluationRequest, user: CurrentUser):
    return evaluate_llm(req)


# ── Health ─────────────────────────────────────────────────────────────────────

@app.get("/health")
@app.get("/v1/health")
def health():
    p_health = get_provider_health()
    model_loaded = (LOADED_CHECKPOINT is not None) or (MODEL is not None)
    provider_ok = bool(p_health.get("available", False))
    return {
        "status": "ok",
        "device": DEVICE,
        "runtime_mode": RUNTIME_MODE,
        "checkpoint": CHECKPOINT,
        "checkpoint_loaded": bool(LOADED_CHECKPOINT),
        "checkpoint_path": LOADED_CHECKPOINT,
        "model_loaded": model_loaded,
        "provider_ok": provider_ok,
        "metadata": META,
        "model_version": MODEL_VERSION,
        "provider": p_health,
    }



# ── Auth endpoints ─────────────────────────────────────────────────────────────

class RegisterRequest(BaseModel):
    username: str
    password: str


class LoginRequest(BaseModel):
    username: str
    password: str


@app.post("/v1/auth/register", status_code=201)
def register(req: RegisterRequest):
    try:
        user = get_auth_db().register(req.username, req.password)
        return {"user_id": user["user_id"], "username": user["username"], "created_at": user["created_at"]}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/v1/auth/login")
def login(req: LoginRequest):
    token = get_auth_db().login(req.username, req.password)
    if token is None:
        raise HTTPException(status_code=401, detail="Tên đăng nhập hoặc mật khẩu không đúng")
    return {"token": token, "token_type": "Bearer"}


@app.post("/v1/auth/logout")
def logout(user: CurrentUser, authorization: Annotated[Optional[str], Header()] = None):
    if authorization and authorization.startswith("Bearer "):
        get_auth_db().logout(authorization[7:])
    return {"ok": True}


@app.get("/v1/auth/me")
def me(user: CurrentUser):
    return {"user_id": user["user_id"], "username": user["username"]}


# ── Memory endpoints ───────────────────────────────────────────────────────────

class MemoryCreateRequest(BaseModel):
    info_type: str = Field(..., description="Loại thông tin: preference, goal, decision, project_fact, ...")
    content: str
    source_session: Optional[str] = None
    project_id: Optional[str] = None


class MemoryUpdateRequest(BaseModel):
    content: str
    info_type: Optional[str] = None
    source_session: Optional[str] = None


@app.post("/v1/memories", status_code=201)
def create_memory(req: MemoryCreateRequest, user: CurrentUser):
    return get_memory_db().create_memory(
        user_id=user["user_id"],
        info_type=req.info_type,
        content=req.content,
        source_session=req.source_session,
        project_id=req.project_id,
    )


@app.get("/v1/memories")
def list_memories(
    user: CurrentUser,
    project_id: Optional[str] = None,
    include_inactive: bool = False,
    search: Optional[str] = None,
    limit: int = 100,
    offset: int = 0,
):
    return get_memory_db().list_memories(
        user_id=user["user_id"],
        project_id=project_id,
        include_inactive=include_inactive,
        search=search,
        limit=min(limit, 200),
        offset=offset,
    )


@app.get("/v1/memories/{memory_id}")
def get_memory(memory_id: str, user: CurrentUser):
    mem = get_memory_db().get_memory(user["user_id"], memory_id)
    if mem is None:
        raise HTTPException(status_code=404, detail="Memory not found")
    return mem


@app.get("/v1/memories/{memory_id}/history")
def get_memory_history(memory_id: str, user: CurrentUser):
    mem = get_memory_db().get_memory(user["user_id"], memory_id)
    if mem is None:
        raise HTTPException(status_code=404, detail="Memory not found")
    return get_memory_db().get_memory_history(user["user_id"], memory_id)


@app.put("/v1/memories/{memory_id}")
def update_memory(memory_id: str, req: MemoryUpdateRequest, user: CurrentUser):
    updated = get_memory_db().update_memory(
        user_id=user["user_id"],
        memory_id=memory_id,
        new_content=req.content,
        new_type=req.info_type,
        source_session=req.source_session,
    )
    if updated is None:
        raise HTTPException(status_code=404, detail="Memory not found")
    return updated


@app.delete("/v1/memories/{memory_id}", status_code=204)
def delete_memory(memory_id: str, user: CurrentUser):
    ok = get_memory_db().delete_memory(user["user_id"], memory_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Memory not found or already inactive")


# ── Project endpoints ──────────────────────────────────────────────────────────

class ProjectCreateRequest(BaseModel):
    name: str
    description: str = ""


@app.post("/v1/projects", status_code=201)
def create_project(req: ProjectCreateRequest, user: CurrentUser):
    return get_memory_db().create_project(user["user_id"], req.name, req.description)


@app.get("/v1/projects")
def list_projects(user: CurrentUser):
    return get_memory_db().list_projects(user["user_id"])


@app.get("/v1/projects/{project_id}")
def get_project(project_id: str, user: CurrentUser):
    proj = get_memory_db().get_project(user["user_id"], project_id)
    if proj is None:
        raise HTTPException(status_code=404, detail="Project not found")
    return proj


@app.get("/v1/projects/{project_id}/decisions")
def get_project_decisions(project_id: str, user: CurrentUser, include_inactive: bool = False):
    """Get memories (decisions) for a project. Active only by default."""
    return get_memory_db().list_memories(
        user_id=user["user_id"],
        project_id=project_id,
        include_inactive=include_inactive,
    )


# ── Chat Session endpoints ─────────────────────────────────────────────────────

class SessionCreateRequest(BaseModel):
    title: Optional[str] = None


@app.post("/v1/sessions", status_code=201)
def create_session(req: SessionCreateRequest, user: CurrentUser):
    return get_memory_db().create_session(user["user_id"], title=req.title)


@app.get("/v1/sessions")
def list_sessions(user: CurrentUser):
    return get_memory_db().list_sessions(user["user_id"])


@app.get("/v1/sessions/{session_id}")
def get_session(session_id: str, user: CurrentUser):
    sess = get_memory_db().get_session(user["user_id"], session_id)
    if sess is None:
        raise HTTPException(status_code=404, detail="Session not found")
    return sess


@app.get("/v1/sessions/{session_id}/messages")
def get_messages(session_id: str, user: CurrentUser, limit: int = 100, offset: int = 0):
    sess = get_memory_db().get_session(user["user_id"], session_id)
    if sess is None:
        raise HTTPException(status_code=404, detail="Session not found")
    return get_memory_db().get_messages(user["user_id"], session_id, limit=limit, offset=offset)


@app.delete("/v1/sessions/{session_id}")
def delete_session(session_id: str, user: CurrentUser):
    ok = get_memory_db().delete_session(user["user_id"], session_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Session not found")
    return {"ok": True}


# ── Chat endpoint (main interaction) ──────────────────────────────────────────

# Patterns that indicate the user wants to modify a decision memory (Vietnamese + English)
_DECISION_MODIFY_PATTERNS = [
    r"(?:tôi muốn|hãy|xin hãy)\s+(?:sửa|thay|cập nhật|đổi|thay đổi|chỉnh)\s+(?:quyết định|lựa chọn|kế hoạch)",
    r"(?:sửa|thay đổi|cập nhật|đổi)\s+(?:quyết định|lựa chọn|kế hoạch)",
    r"(?:không dùng|bỏ|huỷ|hủy)\s+.+(?:nữa|thay vào đó)",
    r"(?:replace|change|update|modify)\s+(?:the\s+)?(?:decision|choice|plan)",
    r"(?:instead of|no longer use|switch from)",
    r"\b(?:đổi|chuyển|thay)\s+.+?\s+(?:sang|thành|bằng)\s+.+",
    r"\b(?:thay đổi|cập nhật)\s+.+?\s+(?:sang|thành|bằng)\s+.+",
]

# Phrases that signal uncertainty or hesitation => return None immediately (ask again)
_CONFIRM_UNCERTAIN_PATTERNS = [
    r"\b(?:không chắc|chưa chắc|không biết|chưa biết|không rõ|chưa rõ|phân vân|đang nghĩ|suy nghĩ lại)\b",
    r"\b(?:khoan|khoan đã|chờ|chờ đã|chờ tí|từ từ|để xem|tùy|tùy vào)\b",
    r"\b(?:hmm|hmmm|maybe|not sure|uncertain|unsure|idk)\b",
]

# Phrases where confirmation words are explicitly negated or cancelled
_CONFIRM_NEGATED_CONFIRMS = [
    r"\b(?:không|chưa|đừng|chẳng)\s+(?:đồng ý|xác nhận|đúng|được|ok|okay|yes|thay|đổi|sửa)\b",
    r"\b(?:không|chưa)\s+có\b",
    r"\bgiữ nguyên(?:\s+như cũ)?\b",
    r"\bthôi\s+đừng(?:\s+thay)?\b",
    r"\bkhông\s+muốn\s+thay\b",
    r"\bkhông\s+cần\s+(?:thay|đổi)\b",
]

# Unambiguous rejection / cancellation patterns
_CONFIRM_REJECT_PATTERNS = [
    r"\b(?:không đồng ý|chưa đồng ý|không xác nhận|chưa xác nhận|không đúng|không được|không ok)\b",
    r"\b(?:đừng thay|đừng đổi|đừng sửa|giữ nguyên|thôi đừng thay|thôi đừng)\b",
    r"\b(?:không muốn thay|không cần thay|không cần đổi)\b",
    r"\b(?:từ chối|bỏ qua|huỷ|hủy|cancel|thôi|đừng|no|nope|không)\b",
]

# Unambiguous confirmation patterns
_CONFIRM_ACCEPT_PATTERNS = [
    r"\b(?:đồng ý|xác nhận|chính xác|chuẩn|tiến hành|làm đi)\b",
    r"\b(?:được|ừ|ok|okay|yes|yep|sure|đúng|có)\b",
]


def _detect_decision_modify_intent(text: str) -> bool:
    """Return True if the message expresses intent to modify an existing decision."""
    import re as _re
    lower = text.lower()
    for pat in _DECISION_MODIFY_PATTERNS:
        if _re.search(pat, lower):
            return True
    return False


def _normalize_confirm_text(text: str) -> str:
    """Normalize Unicode (NFC), lowercase, replace punctuation with spaces, collapse spaces."""
    import unicodedata
    import re as _re
    text = unicodedata.normalize("NFC", text)
    text = text.lower()
    text = _re.sub(r"[^\w\s]", " ", text, flags=_re.UNICODE)
    return _re.sub(r"\s+", " ", text).strip()


def _detect_confirm(text: str) -> Optional[bool]:
    """Return True=confirm, False=reject, None=unclear/contradictory.

    Uses word/phrase-boundary matching after Unicode NFC normalization.
    Negations like 'không đồng ý', 'không đúng', 'đừng thay' are strictly REJECT (False).
    Contradictory signals (e.g. 'có nhưng mà không') or uncertainty ('không chắc') return None.
    Substrings inside words (e.g. 'nói' != 'no', 'cố' != 'có', 'smoke' != 'ok') are ignored.
    """
    import re as _re
    t = _normalize_confirm_text(text)
    if not t:
        return None

    # 1. Uncertainty signals => ask again immediately
    for p in _CONFIRM_UNCERTAIN_PATTERNS:
        if _re.search(p, t):
            return None

    # 2. Mask out negated confirmations before checking accept patterns
    clean_for_confirm = t
    for neg in _CONFIRM_NEGATED_CONFIRMS:
        clean_for_confirm = _re.sub(neg, " ", clean_for_confirm)
    clean_for_confirm = _re.sub(r"\s+", " ", clean_for_confirm).strip()

    has_confirm = any(_re.search(p, clean_for_confirm) for p in _CONFIRM_ACCEPT_PATTERNS)
    has_reject = any(_re.search(p, t) for p in _CONFIRM_REJECT_PATTERNS)

    # 3. Contradictory signals (both confirm and reject cues present) => ask again
    if has_confirm and has_reject:
        return None

    if has_confirm:
        return True
    if has_reject:
        return False
    return None
def _find_best_matching_decision(
    memories: list[dict], message: str
) -> tuple[Optional[dict], bool, list[dict]]:
    """
    Pick the active decision memory most relevant to the message using decision_updater.
    Returns (best_match, is_ambiguous, candidate_list).
    """
    return find_best_matching_decision(memories, message)


_REMEMBER_EXPLICIT_PATTERNS = [
    r"^(?:hãy\s+)?(?:nhớ|ghi nhớ|lưu|lưu lại)\s+(?:rằng|là|quyết định|lựa chọn|kế hoạch)?\s*[:：,]?\s*(.+)$",
    r"^(?:hãy\s+)?lưu\s+(?:quyết định|lựa chọn|ý này)\s*[:：,]?\s*(.+)$",
    r"^(?:nhớ|ghi nhớ)\s+giúp\s+tôi\s+(?:rằng|là)?\s*[:：,]?\s*(.+)$",
]


def _detect_remember_intent(text: str) -> Optional[tuple[str, str]]:
    """
    Check if message is an explicit memory instruction.
    Returns (info_type, clean_content) or None.
    """
    import re as _re
    t = text.strip()
    for pat in _REMEMBER_EXPLICIT_PATTERNS:
        m = _re.search(pat, t, flags=_re.IGNORECASE)
        if m:
            content = m.group(1).strip()
            content = _re.sub(r"[.?!]+$", "", content).strip()
            if not content or len(content) < 3:
                continue
            lower = t.lower()
            if any(w in lower for w in ("quyết định", "lựa chọn", "kế hoạch", "chốt")):
                itype = "decision"
            elif any(w in lower for w in ("ưu tiên", "thích", "muốn")):
                itype = "preference"
            elif any(w in lower for w in ("mục tiêu", "target", "goal")):
                itype = "goal"
            else:
                itype = "decision"
            return itype, content
    return None


def _detect_missing_context_query(text: str) -> bool:
    """Check if user asks for previous context/choice that requires context."""
    import re as _re
    t = text.lower()
    patterns = [
        r"\b(?:cái|điều|ý|nội dung|quyết định|lựa chọn|kế hoạch)\s+(?:vừa nói|trước đó|hôm trước|nãy)\b",
        r"\b(?:tôi vừa nói gì|nhắc lại cái vừa nói|quyết định của tôi là gì)\b",
        # Recall requests referring to a previous period ("tuần trước", "tháng trước", ...).
        r"\bnhắc lại\b",
        r"\b(?:quyết định|lựa chọn|kế hoạch|cấu hình|thiết lập)\b[^?]{0,60}?\b(?:tuần trước|tháng trước|hôm trước|kỳ trước|lần trước|trước đây)\b",
    ]
    return any(_re.search(p, t) for p in patterns)


_PROJECT_SCOPE_QUESTION_PATTERNS = [
    r"\b(?:dự án|dự án này|project)\b[^?]{0,60}\?\s*$",
]


def _detect_project_scoped_question(text: str, project_id: Optional[str]) -> bool:
    """
    True when the user asks a question scoped to an explicit project.

    Such a question must be answered from that project's own active memories; if
    none exist we must clarify rather than let the model answer from nothing.
    Explicit instructions (remember / modify) are never treated as questions.
    """
    import re as _re

    if not project_id:
        return False
    t = text.strip()
    if "?" not in t:
        return False
    if _detect_remember_intent(t) is not None or _detect_decision_modify_intent(t):
        return False
    return any(_re.search(pat, t.lower()) for pat in _PROJECT_SCOPE_QUESTION_PATTERNS)


def _calculate_time_gap_hours(stored: Optional[dict]) -> float:
    if not stored or not stored.get("updated_at"):
        return 0.0
    try:
        from datetime import datetime, timezone
        prev_time = datetime.fromisoformat(stored["updated_at"])
        if prev_time.tzinfo is None:
            prev_time = prev_time.replace(tzinfo=timezone.utc)
        now = datetime.now(timezone.utc)
        diff_hours = (now - prev_time).total_seconds() / 3600.0
        return max(0.0, min(8760.0, diff_hours))
    except Exception:
        return 0.0


def _compute_global_user_id(user_id: str) -> str:
    """Compute a stable global_user_id for a local user_id."""
    identity = f"local:{user_id}"
    import hashlib
    b = hashlib.sha256(identity.encode()).digest()
    return f"{b[0]:02x}{b[1]:02x}{b[2]:02x}{b[3]:02x}-{b[4]:02x}{b[5]:02x}-{b[6]:02x}{b[7]:02x}-{b[8]:02x}{b[9]:02x}-{b[10]:02x}{b[11]:02x}{b[12]:02x}{b[13]:02x}{b[14]:02x}{b[15]:02x}"


def _run_dusnx(
    global_user_id: str,
    platform: str,
    content: str,
    feedback_value: float,
    active_cfg: ModelConfig,
    previous_state_blob: Optional[dict] = None,
    time_gap_hours: float = 0.0,
) -> tuple[str, str, str, float, str, Optional[int], Optional[dict]]:
    """Run DUSN-X model or bootstrap rules.
    Returns (intent, agent, action, confidence, routing_source, state_version, new_state_blob).
    new_state_blob is a JSON-serializable dict for DB storage.
    """
    from dusnx_core.schema import StateSnapshot as _SS

    def _snapshot_from_blob(blob: dict) -> Optional[_SS]:
        try:
            return _SS(**blob)
        except Exception:
            return None

    if MODEL is None:
        # Bootstrap rules path
        previous_snapshot = _snapshot_from_blob(previous_state_blob) if previous_state_blob else None
        from dusnx_core.schema import ProcessRequest as _PR
        req = _PR(
            global_user_id=global_user_id,
            platform=platform,
            content=content,
            event_type="message",
            time_gap_hours=max(0.0, float(time_gap_hours)),
            feedback_value=feedback_value,
            previous_state=previous_snapshot,
        )
        intent, agent, action, conf = detect_route(content)
        new_snapshot = bootstrap_state_update(req, intent)
        new_blob = new_snapshot.model_dump()
        return intent, agent, action, conf, "bootstrap_rules", new_snapshot.state_version, new_blob
    else:
        from dusnx_core.inference import process_one as _process_one
        from dusnx_core.schema import ProcessRequest as _PR
        previous_snapshot = _snapshot_from_blob(previous_state_blob) if previous_state_blob else None
        reset_reason = state_reset_reason(previous_snapshot, active_cfg, MODEL_VERSION)
        if reset_reason:
            previous_snapshot = None
        req = _PR(
            global_user_id=global_user_id,
            platform=platform,
            content=content,
            event_type="message",
            time_gap_hours=max(0.0, float(time_gap_hours)),
            feedback_value=feedback_value,
            previous_state=previous_snapshot,
        )
        result = _process_one(MODEL, CFG, req, MODEL_VERSION, DEVICE)
        version = (previous_snapshot.state_version if previous_snapshot else 0) + 1
        new_snapshot = StateSnapshot(**state_to_snapshot(result["new_state"], version, STATE_SCHEMA_VERSION, MODEL_VERSION))
        new_blob = new_snapshot.model_dump()
        explicit = match_explicit_route(platform, content)
        if explicit is not None:
            return explicit.intent, explicit.agent, explicit.next_action, explicit.confidence, "business_rule_override", version, new_blob
        return result["intent"], result["selected_agent"], result["next_action"], result["confidence"], "model", version, new_blob


def _advance_user_state(
    db,
    user_id: str,
    content: str,
    feedback_value: float = 0.0,
    platform: str = "web",
    event_type: str = "message",
    project_id: Optional[str] = None,
    event_id: Optional[str] = None,
) -> tuple[int, Optional[dict], str, str, str, float, str]:
    """Advance DUSN-X state vector for a user turn and persist to DB atomically."""
    with db._lock:
        if event_id:
            existing = db.get_user_event(user_id, event_id)
            if existing:
                stored = db.get_dusnx_state(user_id)
                return (
                    existing.get("state_version", stored["state_version"] if stored else 1),
                    stored["state_blob"] if stored else None,
                    existing.get("intent", "chat"),
                    existing.get("selected_agent", "conversation"),
                    existing.get("next_action", "reply"),
                    existing.get("confidence", 0.7),
                    "deduplicated_event",
                )

        global_user_id = _compute_global_user_id(user_id)
        stored = db.get_dusnx_state(user_id)
        time_gap = _calculate_time_gap_hours(stored)
        prev_blob = stored["state_blob"] if stored else None
        active_cfg = CFG or ModelConfig()
        intent, agent, action, conf, r_source, s_ver, new_blob = _run_dusnx(
            global_user_id=global_user_id,
            platform=platform,
            content=content,
            feedback_value=feedback_value,
            active_cfg=active_cfg,
            previous_state_blob=prev_blob,
            time_gap_hours=time_gap,
        )
        db.advance_state_and_record_event_atomic(
            user_id=user_id,
            state_blob=new_blob,
            state_version=s_ver or 1,
            platform=platform,
            event_type=event_type,
            content=content,
            project_id=project_id,
            feedback_value=feedback_value,
            event_id=event_id,
            intent=intent,
            selected_agent=agent,
            next_action=action,
            confidence=conf,
        )
        return s_ver or 1, new_blob, intent, agent, action, conf, r_source


class ChatRequest(BaseModel):
    session_id: str
    message: str
    project_id: Optional[str] = None
    feedback_value: float = Field(default=0.0)
    is_retry: bool = Field(default=False)


class ChatResponse(BaseModel):
    message_id: str
    reply: str
    intent: str
    selected_agent: str
    next_action: str
    confidence: float
    runtime_mode: str
    routing_source: str
    provider_used: Optional[str] = None
    provider_ok: bool
    state_version: Optional[int]
    memory_ids_used: list[str]
    session_id: str
    model_used: Optional[str] = None
    tokens_generated: Optional[int] = None
    answer_source: str = "application_rule"
    candidate_memory_ids: list[str] = Field(default_factory=list)
    prompt_memory_ids: list[str] = Field(default_factory=list)
    provider_called: bool = False
    response_source: str = "application_rule"


@app.post("/v1/chat", response_model=ChatResponse)
def chat(req: ChatRequest, user: CurrentUser):
    db = get_memory_db()
    user_id = user["user_id"]

    # Verify session ownership
    sess = db.get_session(user_id, req.session_id)
    if sess is None:
        raise HTTPException(status_code=404, detail="Session not found or not owned by this user")

    # Retry check: prevent duplicate user message
    if req.is_retry:
        last_msgs = db.get_messages(user_id, req.session_id, limit=1)
        if not (last_msgs and last_msgs[0]["role"] == "user" and last_msgs[0]["content"] == req.message):
            db.append_message(req.session_id, user_id, "user", req.message)
    else:
        db.append_message(req.session_id, user_id, "user", req.message)

    # Get active memories for context (filtered and scored by query/project)
    memories = db.get_active_memories_for_context(user_id, project_id=req.project_id, query=req.message, limit=15)
    candidate_ids = [m["memory_id"] for m in memories]
    memory_ids = []

    def chat_response(**kwargs):
        if kwargs.get("next_action") == "clarify" and "response_source" not in kwargs:
            kwargs["response_source"] = "clarification"
        return ChatResponse(candidate_memory_ids=candidate_ids, **kwargs)

    def advance(*args, **kwargs):
        if req.is_retry:
            state = db.get_dusnx_state(user_id)
            if state:
                return state["state_version"], {}, "chat", "conversation", "reply", 0.8, "retry"
        return _advance_user_state(*args, **kwargs)

    # Get recent session history (for context)
    history = db.get_messages(user_id, req.session_id, limit=12)
    # Exclude the just-added user message from history (it's the current input)
    history = history[:-1] if history else []

    # Determine project name if applicable
    project_name = None
    if req.project_id:
        proj = db.get_project(user_id, req.project_id)
        project_name = proj["name"] if proj else None

    # ── Missing context guard ─────────────────────────────────────────────────
    if _detect_missing_context_query(req.message) or _detect_project_scoped_question(req.message, req.project_id):
        has_context = bool(history) or bool(memories)
        if not has_context:
            s_ver, _, _, _, _, _, _ = advance(
                db, user_id, req.message, req.feedback_value, platform="web", event_type="chat_message", project_id=req.project_id
            )
            reply_text = "Hiện tại tôi chưa có bối cảnh hoặc quyết định nào trước đó để nhắc lại. Bạn có thể cho tôi biết bạn muốn trao đổi hay chốt nội dung nào không?"
            msg = db.append_message(
                req.session_id, user_id, "assistant", reply_text,
                memory_ids_used=[], state_version=s_ver,
            )
            return chat_response(
                message_id=msg["message_id"], reply=reply_text,
                intent="clarify_missing_context", selected_agent="conversation",
                next_action="clarify", confidence=0.9,
                runtime_mode=RUNTIME_MODE, routing_source="context_guard",
                provider_used=None, provider_ok=True,
                state_version=s_ver, memory_ids_used=[],
                session_id=req.session_id,
            )

    # ── Explicit memory instruction flow ──────────────────────────────────────
    remember_intent = _detect_remember_intent(req.message)
    if remember_intent is not None:
        itype, clean_content = remember_intent
        new_mem = db.create_memory(
            user_id=user_id,
            info_type=itype,
            content=clean_content,
            source_session=req.session_id,
            project_id=req.project_id,
        )
        s_ver, _, _, _, _, _, _ = advance(
            db, user_id, req.message, req.feedback_value, platform="web", event_type="memory_create", project_id=req.project_id
        )
        reply_text = f"Đã ghi nhớ {itype}: \"{clean_content}\"."
        msg = db.append_message(
            req.session_id, user_id, "assistant", reply_text,
            memory_ids_used=[new_mem["memory_id"]], state_version=s_ver,
        )
        return chat_response(
            message_id=msg["message_id"], reply=reply_text,
            intent="memory_create", selected_agent="memory",
            next_action="create_memory", confidence=0.95,
            runtime_mode=RUNTIME_MODE, routing_source="explicit_memory",
            provider_used=None, provider_ok=True,
            state_version=s_ver, memory_ids_used=[new_mem["memory_id"]],
            session_id=req.session_id,
        )

    # ── Decision modification flow ────────────────────────────────────────────
    # First check: is there a pending confirmation waiting?
    pending = db.get_session_pending_decision(user_id, req.session_id)
    if pending is None and req.is_retry:
        last_p = db.get_last_pending_decision_in_session(user_id, req.session_id)
        if last_p and last_p.get("status") == "confirmed":
            if _detect_confirm(req.message) is True:
                pending = last_p

    if pending is not None:
        confirmed = _detect_confirm(req.message)
        if confirmed is True:
            # Apply supersede atomically in one DB transaction
            res = db.resolve_pending_decision_atomic(
                user_id=user_id,
                pending_id=pending["pending_id"],
                accepted=True,
                source_session=req.session_id,
                allow_idempotent_retry=bool(req.is_retry),
            )
            s_ver, _, _, _, _, _, _ = advance(
                db, user_id, req.message, req.feedback_value, platform="web", event_type="decision_confirm", project_id=req.project_id
            )
            if res["success"]:
                reply_text = (
                    f"✅ Đã cập nhật quyết định.\n"
                    f"**Cũ:** {pending['old_content']}\n"
                    f"**Mới:** {pending['proposed_content']}"
                )
                memory_ids = [res["new_memory"]["memory_id"], pending["old_memory_id"]]
                intent = "decision_update"
                next_action = "update_memory"
            else:
                reply_text = f"⚠️ Không thể cập nhật quyết định: {res['detail']}."
                memory_ids = []
                intent = "decision_update_failed"
                next_action = "clarify"

            msg = db.append_message(
                req.session_id, user_id, "assistant", reply_text,
                memory_ids_used=memory_ids, state_version=s_ver,
            )
            return chat_response(
                message_id=msg["message_id"], reply=reply_text,
                intent=intent, selected_agent="memory",
                next_action=next_action, confidence=1.0,
                runtime_mode=RUNTIME_MODE, routing_source="decision_flow",
                provider_used=None, provider_ok=True,
                state_version=s_ver, memory_ids_used=memory_ids,
                session_id=req.session_id,
            )
        elif confirmed is False:
            db.resolve_pending_decision_atomic(
                user_id=user_id,
                pending_id=pending["pending_id"],
                accepted=False,
                source_session=req.session_id,
            )
            s_ver, _, _, _, _, _, _ = advance(
                db, user_id, req.message, req.feedback_value, platform="web", event_type="decision_reject", project_id=req.project_id
            )
            reply_text = (
                f"Đã huỷ yêu cầu sửa đổi quyết định. Giữ nguyên quyết định hiện tại:\n"
                f"**Hiện tại:** {pending['old_content']}"
            )
            memory_ids = [pending["old_memory_id"]]
            msg = db.append_message(
                req.session_id, user_id, "assistant", reply_text,
                memory_ids_used=memory_ids, state_version=s_ver,
            )
            return chat_response(
                message_id=msg["message_id"], reply=reply_text,
                intent="decision_update_cancelled", selected_agent="memory",
                next_action="no_op", confidence=1.0,
                runtime_mode=RUNTIME_MODE, routing_source="decision_flow",
                provider_used=None, provider_ok=True,
                state_version=s_ver, memory_ids_used=memory_ids,
                session_id=req.session_id,
            )
        else:
            # Ambiguous / uncertain / contradictory — ask again without modifying
            s_ver, _, _, _, _, _, _ = advance(
                db, user_id, req.message, req.feedback_value, platform="web", event_type="decision_unclear", project_id=req.project_id
            )
            reply_text = (
                f"Tôi chưa rõ ý bạn. Bạn có muốn thay đổi quyết định sau không?\n"
                f"**Hiện tại:** {pending['old_content']}\n"
                f"**Đề xuất:** {pending['proposed_content']}\n\n"
                "Trả lời **Có** để xác nhận hoặc **Không** để huỷ."
            )
            memory_ids = [pending["old_memory_id"]]
            msg = db.append_message(
                req.session_id, user_id, "assistant", reply_text,
                memory_ids_used=memory_ids, state_version=s_ver,
            )
            return chat_response(
                message_id=msg["message_id"], reply=reply_text,
                intent="awaiting_confirm", selected_agent="memory",
                next_action="clarify", confidence=0.9,
                runtime_mode=RUNTIME_MODE, routing_source="decision_flow",
                provider_used=None, provider_ok=True,
                state_version=s_ver, memory_ids_used=memory_ids,
                session_id=req.session_id,
            )

    # Second check: does the new message request a decision modification?
    if _detect_decision_modify_intent(req.message):
        matched, is_ambiguous, candidates = _find_best_matching_decision(memories, req.message)
        s_ver, _, _, _, _, _, _ = advance(
            db, user_id, req.message, req.feedback_value, platform="web", event_type="decision_modify_request", project_id=req.project_id
        )
        if is_ambiguous:
            cand_text = "\n".join(f"- {c['content']}" for c in candidates)
            reply_text = (
                "Tôi thấy bạn có nhiều quyết định gần giống nhau liên quan đến nội dung này:\n"
                f"{cand_text}\n\n"
                "Vui lòng nêu rõ nội dung quyết định cụ thể bạn muốn thay đổi."
            )
            msg = db.append_message(
                req.session_id, user_id, "assistant", reply_text,
                memory_ids_used=[c["memory_id"] for c in candidates], state_version=s_ver,
            )
            return chat_response(
                message_id=msg["message_id"], reply=reply_text,
                intent="clarify_ambiguous_decision", selected_agent="memory",
                next_action="clarify", confidence=0.85,
                runtime_mode=RUNTIME_MODE, routing_source="decision_flow",
                provider_used=None, provider_ok=True,
                state_version=s_ver, memory_ids_used=[c["memory_id"] for c in candidates],
                session_id=req.session_id,
            )
        elif matched is not None:
            comps = extract_modify_components(req.message)
            proposed = synthesize_full_decision(
                old_content=matched["content"],
                message=req.message,
                topic=comps["topic"],
                new_value=comps["new_value"],
            )

            db.create_pending_decision(
                user_id=user_id,
                session_id=req.session_id,
                old_memory_id=matched["memory_id"],
                old_content=matched["content"],
                proposed_content=proposed,
                topic=comps["topic"],
                new_value=comps["new_value"],
                statement_source=req.message,
            )
            reply_text = (
                f"Tôi thấy bạn muốn thay đổi quyết định. Bạn có muốn:\n"
                f"**Cũ:** {matched['content']}\n"
                f"**Mới:** {proposed}\n\n"
                "Trả lời **Có** để xác nhận hoặc **Không** để huỷ."
            )
            msg = db.append_message(
                req.session_id, user_id, "assistant", reply_text,
                memory_ids_used=[matched["memory_id"]], state_version=s_ver,
            )
            return chat_response(
                message_id=msg["message_id"], reply=reply_text,
                intent="decision_modify_intent", selected_agent="memory",
                next_action="await_confirm", confidence=0.88,
                runtime_mode=RUNTIME_MODE, routing_source="decision_flow",
                provider_used=None, provider_ok=True,
                state_version=s_ver, memory_ids_used=[matched["memory_id"]],
                session_id=req.session_id,
            )
        else:
            # No matching decision found — ask clarifying question
            reply_text = (
                "Tôi chưa tìm thấy quyết định nào phù hợp để sửa. "
                "Bạn có thể mô tả rõ hơn quyết định nào cần thay đổi không?"
            )
            msg = db.append_message(
                req.session_id, user_id, "assistant", reply_text,
                memory_ids_used=[], state_version=s_ver,
            )
            return chat_response(
                message_id=msg["message_id"], reply=reply_text,
                intent="decision_modify_intent", selected_agent="memory",
                next_action="clarify", confidence=0.7,
                runtime_mode=RUNTIME_MODE, routing_source="decision_flow",
                provider_used=None, provider_ok=True,
                state_version=s_ver, memory_ids_used=[],
                session_id=req.session_id,
            )

    # ── Normal chat flow ──────────────────────────────────────────────────────
    if req.is_retry:
        st = db.get_dusnx_state(user_id)
        state_version = st["state_version"] if st else 1
        dusnx_intent = "chat"
        dusnx_agent = "conversation"
        dusnx_action = "reply"
        confidence = 0.8
        routing_source = "retry"
    else:
        state_version, _, dusnx_intent, dusnx_agent, dusnx_action, confidence, routing_source = advance(
            db,
            user_id=user_id,
            content=req.message,
            feedback_value=req.feedback_value,
            platform="web",
            event_type="chat_message",
            project_id=req.project_id,
        )

    # A template is selected before any provider call. Never discard generated
    # text while attributing a deterministic quotation to its model/provider.
    grounded_answer, selected = memory_answer_with_selection(req.message, memories)
    prompt_ids = []
    provider_called = False
    if grounded_answer is not None:
        reply_text, provider_ok = grounded_answer, True
        provider_used = model_used = tokens_generated = None
        response_source = "grounded_template" if selected else "clarification"
        memory_ids = [m["memory_id"] for m in selected]
        if not selected:
            dusnx_intent, dusnx_agent, dusnx_action = "clarify_missing_context", "conversation", "clarify"
            routing_source = "context_guard"
    else:
        selected = select_memories(req.message, memories)
        prompt_ids = [m["memory_id"] for m in selected]
        generated = generate_response(
            user_message=req.message, memories=selected, intent=dusnx_intent,
            session_history=history, project_name=project_name,
        )
        reply_text, provider_ok, provider_used, model_used, tokens_generated = generated
        provider_called = getattr(generated, "provider_called", False)
        response_source = ("llm" if provider_called else "mock") if provider_ok else "provider_error"
        if not provider_called:
            provider_used = model_used = tokens_generated = None
        # LLM citations are not measured. Prompt inclusion is reported separately;
        # do not invent evidence attribution from lexical overlap with its output.
        memory_ids = []

    if provider_ok:
        # Save assistant message only on success
        msg = db.append_message(
            req.session_id,
            user_id,
            "assistant",
            reply_text,
            memory_ids_used=memory_ids,
            state_version=state_version,
        )
        msg_id = msg["message_id"]
    else:
        # DO NOT save provider error as a valid assistant message in history
        import uuid as _uuid
        msg_id = f"err_{_uuid.uuid4().hex[:12]}"
        if not reply_text.startswith("["):
            reply_text = f"[Lỗi Provider {provider_used}]: {reply_text}"

    # Auto-update session title from first user message
    if len(history) == 0:
        title = req.message[:60].strip()
        if title:
            db.update_session_title(user_id, req.session_id, title)

    return chat_response(
        message_id=msg_id,
        reply=reply_text,
        intent=dusnx_intent,
        selected_agent=dusnx_agent,
        next_action=dusnx_action,
        confidence=confidence,
        runtime_mode=RUNTIME_MODE,
        routing_source=routing_source,
        provider_used=provider_used,
        provider_ok=provider_ok,
        state_version=state_version,
        memory_ids_used=memory_ids if provider_ok else [],
        session_id=req.session_id,
        model_used=model_used if provider_ok else None,
        tokens_generated=tokens_generated if provider_ok else None,
        answer_source="active_memory_extract" if grounded_answer is not None else "provider",
        prompt_memory_ids=prompt_ids,
        provider_called=provider_called,
        response_source=response_source,
    )


# ── Authenticated User State & Event endpoints (/v1/me/...) ───────────────────

class UserEventCreateRequest(BaseModel):
    platform: str = Field(default="web", description="Platform: web, powerpoint, zalo, ...")
    event_type: str = Field(default="message", description="Event type: message, slide_change, action, ...")
    content: str = Field(..., description="Event content text")
    project_id: Optional[str] = None
    feedback_value: float = Field(default=0.0)
    event_id: Optional[str] = None


@app.post("/v1/me/events", status_code=201)
def create_my_event(req: UserEventCreateRequest, user: CurrentUser):
    """
    Authenticated event ingestion for the logged-in user.
    Uses the exact same state store as Web chat.
    user_id is strictly resolved from Bearer token.
    """
    db = get_memory_db()
    user_id = user["user_id"]

    # Check for deduplication
    if req.event_id:
        existing = db.get_user_event(user_id, req.event_id)
        if existing:
            st = db.get_dusnx_state(user_id)
            return {
                "status": "already_processed",
                "event_id": req.event_id,
                "user_id": user_id,
                "platform": existing["platform"],
                "event_type": existing["event_type"],
                "state_version": existing["state_version"],
                "intent": existing["intent"],
                "selected_agent": existing["selected_agent"],
                "next_action": existing["next_action"],
                "confidence": existing["confidence"],
                "created_at": existing["created_at"],
            }

    s_ver, _, intent, agent, action, conf, routing_source = _advance_user_state(
        db=db,
        user_id=user_id,
        content=req.content,
        feedback_value=req.feedback_value,
        platform=req.platform,
        event_type=req.event_type,
        project_id=req.project_id,
        event_id=req.event_id,
    )
    return {
        "status": "recorded",
        "event_id": req.event_id,
        "user_id": user_id,
        "platform": req.platform,
        "event_type": req.event_type,
        "state_version": s_ver,
        "intent": intent,
        "selected_agent": agent,
        "next_action": action,
        "confidence": conf,
        "routing_source": routing_source,
    }


@app.get("/v1/me/state")
def get_my_state(user: CurrentUser):
    """Get authoritative DUSN-X state for the authenticated user."""
    db = get_memory_db()
    st = db.get_dusnx_state(user["user_id"])
    if not st:
        return {
            "user_id": user["user_id"],
            "state_version": 0,
            "state_schema_version": STATE_SCHEMA_VERSION,
            "model_version": MODEL_VERSION,
            "state_blob": None,
            "updated_at": None,
        }
    return {
        "user_id": user["user_id"],
        "state_version": st["state_version"],
        "state_schema_version": STATE_SCHEMA_VERSION,
        "model_version": MODEL_VERSION,
        "state_blob": st["state_blob"],
        "updated_at": st["updated_at"],
    }


@app.get("/v1/me/events")
def get_my_events(
    user: CurrentUser,
    platform: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
):
    """Get chronological events / timeline for the authenticated user."""
    db = get_memory_db()
    events = db.list_user_events(
        user_id=user["user_id"],
        platform=platform,
        limit=min(limit, 100),
        offset=offset,
    )
    return {"events": events, "count": len(events)}



# ── Pending Decision API endpoints ─────────────────────────────────────────────

@app.get("/v1/pending-decisions")
def list_pending_decisions(user: CurrentUser, session_id: Optional[str] = None):
    """List all awaiting_confirm pending decision updates for the current user."""
    db = get_memory_db()
    if session_id:
        pending = db.get_session_pending_decision(user["user_id"], session_id)
        return [pending] if pending else []
    # General: query all awaiting
    rows = db._conn.execute(
        """SELECT * FROM pending_decision_updates
           WHERE user_id=? AND status='awaiting_confirm'
           ORDER BY created_at DESC""",
        (user["user_id"],),
    ).fetchall()
    return [dict(r) for r in rows]


class ResolvePendingRequest(BaseModel):
    accepted: bool


@app.post("/v1/pending-decisions/{pending_id}/resolve")
def resolve_pending_decision(pending_id: str, req: ResolvePendingRequest, user: CurrentUser):
    """Explicitly confirm or reject a pending decision update via API."""
    db = get_memory_db()
    result = db.resolve_pending_decision_atomic(
        user_id=user["user_id"],
        pending_id=pending_id,
        accepted=req.accepted,
    )
    if not result["success"]:
        if result["error"] in ("not_found", "already_confirmed", "already_rejected", "already_stale"):
            raise HTTPException(status_code=404, detail=result["detail"])
        elif result["error"] == "stale_memory":
            raise HTTPException(status_code=409, detail=result["detail"])
        else:
            raise HTTPException(status_code=400, detail=result["detail"])

    if req.accepted:
        return {"resolved": result["pending"], "updated_memory": result["new_memory"]}
    return {"resolved": result["pending"]}


# ── Legacy /v1/process endpoint (kept for Gateway compatibility) ────────────────

def detect_route(content: str) -> tuple[str, str, str, float]:
    explicit = match_explicit_route("web", content)
    if explicit is not None:
        return explicit.intent, explicit.agent, explicit.next_action, explicit.confidence
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
        state_schema_version=STATE_SCHEMA_VERSION,
        model_version=MODEL_VERSION,
    )


def bootstrap_state_update(req: ProcessRequest, intent: str) -> StateSnapshot:
    previous = req.previous_state or initial_bootstrap_state()
    decay = math.exp(-0.015 * max(0.0, req.time_gap_hours))
    global_state = [value * decay for value in previous.global_state]
    platform_states = [row[:] for row in previous.platform_states]
    task_state = [value * decay for value in previous.task_state]

    words = re.findall(r"\w+", req.content.casefold(), flags=re.UNICODE) or [req.content]
    for word in words:
        import hashlib
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
        state_schema_version=STATE_SCHEMA_VERSION,
        model_version=MODEL_VERSION,
    )


def requested_slide_count(content: str) -> int:
    match = re.search(r"(?:create|tạo)\s+(\d{1,2})\s+slide", content.casefold())
    if not match:
        return 5
    return max(1, min(20, int(match.group(1))))


def build_slide_outline(content: str) -> list[dict]:
    count = requested_slide_count(content)
    topic = re.sub(r"^(?:create|tạo)\s+\d{1,2}\s+slides?\.\?\s*", "", content, flags=re.I).strip()
    topic = topic or "DUSN-X"
    slides = []
    for index in range(1, count + 1):
        slides.append({
            "index": index,
            "title": f"{topic} — phần {index}",
            "bullets": [
                f"Mục tiêu của phần {index}",
                "Luận điểm hoặc dữ liệu cần trình bày",
                "Kết nối với trạng thái người dùng DUSN-X",
            ],
        })
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

    active_cfg = CFG or ModelConfig()
    reset_reason = state_reset_reason(req.previous_state, active_cfg, MODEL_VERSION)
    state_reset = reset_reason is not None
    effective_req = req.model_copy(update={"previous_state": None}) if state_reset else req

    if MODEL is None:
        intent, agent, next_action, confidence = detect_route(req.content)
        snapshot = bootstrap_state_update(effective_req, intent)
        routing_source = "bootstrap_rules"
    else:
        result = process_one(MODEL, CFG, effective_req, MODEL_VERSION, DEVICE)
        intent = result["intent"]
        agent = result["selected_agent"]
        next_action = result["next_action"]
        confidence = result["confidence"]
        version = (effective_req.previous_state.state_version if effective_req.previous_state else 0) + 1
        snapshot = StateSnapshot(**state_to_snapshot(result["new_state"], version, STATE_SCHEMA_VERSION, MODEL_VERSION))
        routing_source = "model"

        explicit = match_explicit_route(req.platform, req.content)
        if explicit is not None and (
            intent != explicit.intent or agent != explicit.agent or next_action != explicit.next_action
        ):
            intent = explicit.intent
            agent = explicit.agent
            next_action = explicit.next_action
            confidence = explicit.confidence
            routing_source = "business_rule_override"

    return ProcessResponse(
        global_user_id=req.global_user_id,
        intent=intent,
        selected_agent=agent,
        next_action=next_action,
        confidence=confidence,
        state_snapshot=snapshot,
        runtime_mode=RUNTIME_MODE,
        routing_source=routing_source,
        agent_output=execute_demo_agent(agent, req, intent, next_action),
        state_reset=state_reset,
        reset_reason=reset_reason,
    )
