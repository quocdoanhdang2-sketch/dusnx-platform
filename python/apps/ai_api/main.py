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

# ── Model loading (unchanged from Phase 1) ─────────────────────────────────────
SOURCE_ROOT = Path(__file__).resolve().parents[2]
ARTIFACT_ROOT = SOURCE_ROOT.parent if SOURCE_ROOT.name == "python" else SOURCE_ROOT
DEFAULT_CHECKPOINT = str(ARTIFACT_ROOT / "artifacts" / "dusnx_smoke_v2.pt")
CHECKPOINT = os.getenv("DUSNX_CHECKPOINT", DEFAULT_CHECKPOINT)
DEVICE = "cuda" if torch.cuda.is_available() and os.getenv("DUSNX_DEVICE", "auto") != "cpu" else "cpu"
MODEL = None
CFG: ModelConfig | None = None
META: dict = {}
RUNTIME_MODE = "bootstrap_rules"
MODEL_VERSION = model_identifier(CHECKPOINT, ModelConfig(), RUNTIME_MODE)
LOADED_CHECKPOINT: str | None = None


def load_model_once() -> None:
    global MODEL, CFG, META, RUNTIME_MODE, MODEL_VERSION, LOADED_CHECKPOINT
    if MODEL is not None:
        return
    path = Path(CHECKPOINT)
    if not path.exists():
        missing_path = path.resolve()
        CFG = ModelConfig()
        META = {
            "mode": "bootstrap_rules",
            "warning": (
                f"Checkpoint not found: {missing_path}. From the repository root, run: "
                "python python/scripts/generate_synthetic.py --events 30000 --users 1000 "
                "--out data/synthetic_30k_v2.jsonl; then "
                "python python/scripts/train.py --config configs/smoke_v2.yaml"
            ),
        }
        RUNTIME_MODE = "bootstrap_rules"
        MODEL_VERSION = model_identifier(CHECKPOINT, CFG, RUNTIME_MODE)
        LOADED_CHECKPOINT = None
        return
    MODEL, CFG, META = load_checkpoint(path, DEVICE)
    RUNTIME_MODE = "trained_dusnx"
    MODEL_VERSION = model_identifier(CHECKPOINT, CFG, RUNTIME_MODE)
    LOADED_CHECKPOINT = str(path.resolve())


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


# ── Health ─────────────────────────────────────────────────────────────────────

@app.get("/health")
def health():
    return {
        "status": "ok",
        "device": DEVICE,
        "runtime_mode": RUNTIME_MODE,
        "checkpoint": CHECKPOINT,
        "checkpoint_loaded": LOADED_CHECKPOINT,
        "metadata": META,
        "model_version": MODEL_VERSION,
        "provider": get_provider_health(),
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
]

# Patterns indicating confirmation (yes) or rejection (no)
_CONFIRM_YES_PATTERNS = ["có", "đồng ý", "xác nhận", "ok", "yes", "sure", "đúng", "được", "ừ"]
_CONFIRM_NO_PATTERNS = ["không", "bỏ qua", "huỷ", "hủy", "no", "cancel", "thôi", "đừng"]


def _detect_decision_modify_intent(text: str) -> bool:
    """Return True if the message expresses intent to modify an existing decision."""
    import re as _re
    lower = text.lower()
    for pat in _DECISION_MODIFY_PATTERNS:
        if _re.search(pat, lower):
            return True
    return False


def _detect_confirm(text: str) -> Optional[bool]:
    """Return True=confirm, False=reject, None=unclear.

    Handles ambiguous phrases by checking uncertainty qualifiers
    before treating words like 'kh\u00f4ng' as a rejection.
    """
    lower = text.strip().lower()
    # Phrases that signal genuine uncertainty => return None immediately
    _UNCERTAIN_PHRASES = (
        "kh\u00f4ng ch\u1eafc", "ch\u01b0a ch\u1eafc",
        "kh\u00f4ng bi\u1ebft", "ch\u01b0a bi\u1ebft",
        "hmm", "kh\u00f4ng r\u00f5",
    )
    if any(p in lower for p in _UNCERTAIN_PHRASES):
        return None
    # Check yes patterns first
    for w in _CONFIRM_YES_PATTERNS:
        if w in lower:
            return True
    # Check no patterns
    for w in _CONFIRM_NO_PATTERNS:
        if w in lower:
            return False
    return None
def _find_best_matching_decision(
    memories: list[dict], message: str
) -> Optional[dict]:
    """Best-effort: pick the active decision memory most relevant to the message."""
    decisions = [m for m in memories if m["info_type"] in ("decision", "preference", "goal")]
    if not decisions:
        return None
    # Simple keyword overlap score
    words = set(message.lower().split())
    best, best_score = None, 0
    for mem in decisions:
        overlap = len(words & set(mem["content"].lower().split()))
        if overlap > best_score:
            best_score = overlap
            best = mem
    return best  # may be None if no overlap — caller handles


class ChatRequest(BaseModel):
    session_id: str
    message: str
    project_id: Optional[str] = None
    feedback_value: float = Field(default=0.0)


class ChatResponse(BaseModel):
    message_id: str
    reply: str
    intent: str
    selected_agent: str
    next_action: str
    confidence: float
    runtime_mode: str
    routing_source: str
    provider_used: str
    provider_ok: bool
    state_version: Optional[int]
    memory_ids_used: list[str]
    session_id: str


@app.post("/v1/chat", response_model=ChatResponse)
def chat(req: ChatRequest, user: CurrentUser):
    db = get_memory_db()
    user_id = user["user_id"]

    # Verify session ownership
    sess = db.get_session(user_id, req.session_id)
    if sess is None:
        raise HTTPException(status_code=404, detail="Session not found or not owned by this user")

    # Save user message
    db.append_message(req.session_id, user_id, "user", req.message)

    # Get active memories for context
    memories = db.get_active_memories_for_context(user_id, project_id=req.project_id, limit=20)
    memory_ids = [m["memory_id"] for m in memories]

    # Get recent session history (for context)
    history = db.get_messages(user_id, req.session_id, limit=12)
    # Exclude the just-added user message from history (it's the current input)
    history = history[:-1] if history else []

    # Determine project name if applicable
    project_name = None
    if req.project_id:
        proj = db.get_project(user_id, req.project_id)
        project_name = proj["name"] if proj else None

    # ── Decision modification flow ────────────────────────────────────────────
    # First check: is there a pending confirmation waiting?
    pending = db.get_session_pending_decision(user_id, req.session_id)
    if pending is not None:
        confirmed = _detect_confirm(req.message)
        if confirmed is True:
            # Apply the supersede
            db.resolve_pending_decision(user_id, pending["pending_id"], accepted=True)
            updated = db.update_memory(
                user_id=user_id,
                memory_id=pending["old_memory_id"],
                new_content=pending["proposed_content"],
                source_session=req.session_id,
            )
            reply_text = (
                f"✅ Đã cập nhật quyết định.\n"
                f"**Cũ:** {pending['old_content']}\n"
                f"**Mới:** {pending['proposed_content']}"
            )
            if updated:
                memory_ids = [updated["memory_id"]]
            msg = db.append_message(
                req.session_id, user_id, "assistant", reply_text,
                memory_ids_used=memory_ids, state_version=None,
            )
            return ChatResponse(
                message_id=msg["message_id"], reply=reply_text,
                intent="decision_update", selected_agent="memory",
                next_action="update_memory", confidence=1.0,
                runtime_mode=RUNTIME_MODE, routing_source="decision_flow",
                provider_used="none", provider_ok=True,
                state_version=None, memory_ids_used=memory_ids,
                session_id=req.session_id,
            )
        elif confirmed is False:
            db.resolve_pending_decision(user_id, pending["pending_id"], accepted=False)
            reply_text = "Đã huỷ yêu cầu sửa đổi quyết định."
            msg = db.append_message(
                req.session_id, user_id, "assistant", reply_text,
                memory_ids_used=[], state_version=None,
            )
            return ChatResponse(
                message_id=msg["message_id"], reply=reply_text,
                intent="decision_update_cancelled", selected_agent="memory",
                next_action="no_op", confidence=1.0,
                runtime_mode=RUNTIME_MODE, routing_source="decision_flow",
                provider_used="none", provider_ok=True,
                state_version=None, memory_ids_used=[],
                session_id=req.session_id,
            )
        else:
            # Ambiguous — ask again
            reply_text = (
                f"Bạn có muốn thay đổi quyết định sau không?\n"
                f"**Hiện tại:** {pending['old_content']}\n"
                f"**Đề xuất:** {pending['proposed_content']}\n\n"
                "Trả lời **Có** để xác nhận hoặc **Không** để huỷ."
            )
            msg = db.append_message(
                req.session_id, user_id, "assistant", reply_text,
                memory_ids_used=[], state_version=None,
            )
            return ChatResponse(
                message_id=msg["message_id"], reply=reply_text,
                intent="awaiting_confirm", selected_agent="memory",
                next_action="clarify", confidence=0.9,
                runtime_mode=RUNTIME_MODE, routing_source="decision_flow",
                provider_used="none", provider_ok=True,
                state_version=None, memory_ids_used=[],
                session_id=req.session_id,
            )

    # Second check: does the new message request a decision modification?
    if _detect_decision_modify_intent(req.message):
        matched = _find_best_matching_decision(memories, req.message)
        if matched is not None:
            # Extract proposed new content: text after keywords like "thành", "sang", "bằng", "to"
            import re as _re
            proposed = _re.sub(
                r"^.+?(?:thành|sang|bằng|to|with|use|dùng)\s+",
                "",
                req.message,
                flags=_re.IGNORECASE,
            ).strip() or req.message
            pending_rec = db.create_pending_decision(
                user_id=user_id,
                session_id=req.session_id,
                old_memory_id=matched["memory_id"],
                old_content=matched["content"],
                proposed_content=proposed,
            )
            reply_text = (
                f"Tôi thấy bạn muốn thay đổi quyết định. Bạn có muốn:\n"
                f"**Cũ:** {matched['content']}\n"
                f"**Mới:** {proposed}\n\n"
                "Trả lời **Có** để xác nhận hoặc **Không** để huỷ."
            )
            msg = db.append_message(
                req.session_id, user_id, "assistant", reply_text,
                memory_ids_used=[matched["memory_id"]], state_version=None,
            )
            return ChatResponse(
                message_id=msg["message_id"], reply=reply_text,
                intent="decision_modify_intent", selected_agent="memory",
                next_action="await_confirm", confidence=0.88,
                runtime_mode=RUNTIME_MODE, routing_source="decision_flow",
                provider_used="none", provider_ok=True,
                state_version=None, memory_ids_used=[matched["memory_id"]],
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
                memory_ids_used=[], state_version=None,
            )
            return ChatResponse(
                message_id=msg["message_id"], reply=reply_text,
                intent="decision_modify_intent", selected_agent="memory",
                next_action="clarify", confidence=0.7,
                runtime_mode=RUNTIME_MODE, routing_source="decision_flow",
                provider_used="none", provider_ok=True,
                state_version=None, memory_ids_used=[],
                session_id=req.session_id,
            )

    # ── Normal chat flow ──────────────────────────────────────────────────────
    global_user_id = _compute_global_user_id(user_id)

    # Load previous persistent state from DB
    stored = db.get_dusnx_state(user_id)
    previous_state_blob = stored["state_blob"] if stored else None

    # Run DUSN-X routing/state update with persistent previous_state
    active_cfg = CFG or ModelConfig()
    dusnx_intent, dusnx_agent, dusnx_action, confidence, routing_source, state_version, new_state_blob = _run_dusnx(
        global_user_id=global_user_id,
        platform="web",
        content=req.message,
        feedback_value=req.feedback_value,
        active_cfg=active_cfg,
        previous_state_blob=previous_state_blob,
    )

    # Persist the updated state back to DB
    if new_state_blob is not None:
        db.set_dusnx_state(user_id, new_state_blob, state_version or 1)

    # Generate text response using provider
    reply_text, provider_ok, provider_used = generate_response(
        user_message=req.message,
        memories=memories,
        intent=dusnx_intent,
        session_history=history,
        project_name=project_name,
    )

    # Save assistant message
    msg = db.append_message(
        req.session_id,
        user_id,
        "assistant",
        reply_text,
        memory_ids_used=memory_ids,
        state_version=state_version,
    )

    # Auto-update session title from first user message
    if len(history) == 0:
        title = req.message[:60].strip()
        if title:
            db.update_session_title(user_id, req.session_id, title)

    return ChatResponse(
        message_id=msg["message_id"],
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
        memory_ids_used=memory_ids,
        session_id=req.session_id,
    )


def _compute_global_user_id(user_id: str) -> str:
    """Compute a stable global_user_id for a local user_id."""
    identity = f"local:{user_id}"
    import hashlib
    import struct
    b = hashlib.sha256(identity.encode()).digest()
    return f"{b[0]:02x}{b[1]:02x}{b[2]:02x}{b[3]:02x}-{b[4]:02x}{b[5]:02x}-{b[6]:02x}{b[7]:02x}-{b[8]:02x}{b[9]:02x}-{b[10]:02x}{b[11]:02x}{b[12]:02x}{b[13]:02x}{b[14]:02x}{b[15]:02x}"


def _run_dusnx(
    global_user_id: str,
    platform: str,
    content: str,
    feedback_value: float,
    active_cfg: ModelConfig,
    previous_state_blob: Optional[dict] = None,
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
            time_gap_hours=0.0,
            feedback_value=feedback_value,
            previous_state=previous_snapshot,
        )
        intent, agent, action, conf = detect_route(content)
        new_snapshot = bootstrap_state_update(req, intent)
        new_blob = new_snapshot.model_dump()
        return intent, agent, action, conf, "bootstrap_rules", new_snapshot.state_version, new_blob
    else:
        import torch as _torch
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
            time_gap_hours=0.0,
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
    resolved = db.resolve_pending_decision(user["user_id"], pending_id, accepted=req.accepted)
    if resolved is None:
        raise HTTPException(status_code=404, detail="Pending decision not found or already resolved")
    if req.accepted:
        pending = resolved
        updated = db.update_memory(
            user_id=user["user_id"],
            memory_id=pending["old_memory_id"],
            new_content=pending["proposed_content"],
        )
        return {"resolved": resolved, "updated_memory": updated}
    return {"resolved": resolved}


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
