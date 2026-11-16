"""Deterministic signal encoding for work sessions.

A chat log is raw signal: text, tool use, corrections, outcomes. This module
turns one session into a typed, content-free record (intent, entities, outcome,
corrections) that can be reviewed, counted, and later used to decide which
turns are worth training on. It never calls a model, so the same session always
encodes to the same record.
"""
from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from dataclasses import dataclass, field

INTENTS = ("question", "instruction", "correction", "approval", "memory_write",
           "statement", "unknown")
OUTCOMES = ("answered", "refused", "error", "not_applicable")

_QUESTION_START = re.compile(
    r"^(?:gi|gì|nao|nào|sao|the nao|thế nào|bao nhieu|bao nhiêu|dau|đâu|ai|"
    r"khi nao|khi nào|vi sao|vì sao|tai sao|tại sao|lam sao|làm sao|cach|cách|"
    r"what|how|why|when|where|which|who)\b")
_INSTRUCTION_START = re.compile(
    r"^(?:hay|hãy|lam|làm|viet|viết|sua|sửa|tao|tạo|chay|chạy|mo|mở|doi|đổi|"
    r"xoa|xóa|them|thêm|kiem|kiểm|build|fix|add|remove|update|run|open|check)\b")
_CORRECTION = re.compile(
    r"\b(?:sai|khong dung|không đúng|nham|nhầm|chua dung|chưa đúng|"
    r"khong phai|không phải|sua lai|sửa lại)\b")
_APPROVAL = re.compile(
    r"^(?:ok|oke|okay|duoc|được|dung|đúng|chuan|chuẩn|uh|vang|vâng)\b|"
    r"\b(?:dong y|đồng ý)\b")
_MEMORY_WRITE = re.compile(
    r"\b(?:nho|nhớ|ghi nho|ghi nhớ|luu lai|lưu lại|tu gio|từ giờ|remember)\b")
_REFUSAL = re.compile(
    r"\b(?:khong tim thay|không tìm thấy|khong co thong tin|không có thông tin|"
    r"chua co du lieu|chưa có dữ liệu|ngoai pham vi|ngoài phạm vi|"
    r"khong the|không thể|khong ho tro|không hỗ trợ|minh khong biet|mình không biết)\b")
_ERROR = re.compile(r"^(?:loi|lỗi|error|exception|traceback|\d{3}\b)\s*[:.\-]?", re.IGNORECASE)

_EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+")
_SECRET = re.compile(r"\b(?:sk-[A-Za-z0-9_-]{12,}|ghp_[A-Za-z0-9]{20,}|AIza[A-Za-z0-9_-]{20,}|Bearer\s+\S+)\b")
_HEX = re.compile(r"\b[0-9a-fA-F]{32,}\b")

_PATH = re.compile(
    r"(?:[A-Za-z]:\\|/)?[\w.-]+(?:[/\\][\w.-]+)+\.(?:md|py|js|ts|json|yaml|yml|cs|csproj|"
    r"html|css|txt|docx|pptx|xlsx|db|gguf|safetensors)\b")
_PORT = re.compile(r"\b(?:localhost|127\.0\.0\.1):(\d{2,5})\b|\bcong\s+(\d{2,5})\b|\bport\s+(\d{2,5})\b")
_COMMAND = re.compile(
    r"\b(?:node|python3?|dotnet|npm|npx|docker|curl|ollama|git|pwsh|powershell|pip)\s+[^\n]+")
_ENV = re.compile(r"\b[A-Z][A-Z0-9]*(?:_[A-Z0-9]+)+\b")
_IDENTIFIER = re.compile(
    r"\b[a-z][a-z0-9]*(?:_[a-z0-9]+)+\b|\b[A-Z][a-z0-9]+(?:[A-Z][a-z0-9]+)+\b")


def fold(text: str) -> str:
    lowered = (text or "").lower().replace("đ", "d")
    decomposed = unicodedata.normalize("NFD", lowered)
    return "".join(ch for ch in decomposed if unicodedata.category(ch) != "Mn")


def scrub(text: str) -> str:
    """Remove secrets and personal identifiers before anything is stored."""
    cleaned = _SECRET.sub("[REDACTED_SECRET]", text or "")
    cleaned = _EMAIL.sub("[REDACTED_EMAIL]", cleaned)
    return _HEX.sub("[REDACTED_HEX]", cleaned)


def _unique(values: list[str], limit: int = 20) -> list[str]:
    seen: list[str] = []
    for value in values:
        value = value.strip()
        if value and value not in seen:
            seen.append(value)
        if len(seen) >= limit:
            break
    return seen


def extract_entities(text: str) -> dict[str, list[str]]:
    raw = text or ""
    ports = [next(group for group in match if group) for match in _PORT.findall(raw)]
    return {
        "path": _unique(_PATH.findall(raw)),
        "port": _unique(ports),
        "command": _unique([line.strip() for line in _COMMAND.findall(raw)]),
        "env": _unique(_ENV.findall(raw)),
        "identifier": _unique(_IDENTIFIER.findall(raw)),
    }


def classify_intent(text: str, role: str = "user") -> str:
    if role != "user":
        return "statement"
    folded = fold(text).strip()
    if not folded:
        return "unknown"
    if _CORRECTION.search(folded):
        return "correction"
    if _APPROVAL.search(folded):
        return "approval"
    if _MEMORY_WRITE.search(folded):
        return "memory_write"
    if _INSTRUCTION_START.search(folded):
        return "instruction"
    if "?" in text or _QUESTION_START.search(folded):
        return "question"
    return "statement"


def classify_outcome(text: str, role: str) -> str:
    if role != "assistant":
        return "not_applicable"
    folded = fold(text)
    if _ERROR.search(text or "") and len(text.strip()) < 200:
        return "error"
    if _REFUSAL.search(folded):
        return "refused"
    return "answered"


@dataclass
class SessionSignal:
    turns: list[dict] = field(default_factory=list)
    platforms: list[str] = field(default_factory=list)

    def counts(self, key: str) -> dict[str, int]:
        result: dict[str, int] = {}
        for turn in self.turns:
            value = turn.get(key)
            if value:
                result[value] = result.get(value, 0) + 1
        return dict(sorted(result.items()))

    def as_record(self, session_id: str | None = None) -> dict:
        entity_kinds: dict[str, int] = {}
        entity_total = 0
        for turn in self.turns:
            for kind, values in turn["entities"].items():
                if values:
                    entity_kinds[kind] = entity_kinds.get(kind, 0) + len(values)
                    entity_total += len(values)
        signature_source = json.dumps(
            [[turn["role"], turn["intent"], turn["outcome"], turn["entities"]] for turn in self.turns],
            ensure_ascii=False, sort_keys=True)
        record = {
            "turn_count": len(self.turns),
            "user_turns": sum(1 for turn in self.turns if turn["role"] == "user"),
            "assistant_turns": sum(1 for turn in self.turns if turn["role"] == "assistant"),
            "intents": self.counts("intent"),
            "outcomes": self.counts("outcome"),
            "platforms": sorted(set(self.platforms)),
            "entity_kinds": dict(sorted(entity_kinds.items())),
            "entity_total": entity_total,
            "has_correction": any(turn["intent"] == "correction" for turn in self.turns),
            "has_memory_write": any(turn["intent"] == "memory_write" for turn in self.turns),
            "signature": hashlib.sha256(signature_source.encode("utf-8")).hexdigest()[:16],
        }
        if session_id:
            record["session_id"] = session_id
        return record


def encode_turn(role: str, content: str) -> dict:
    clean = scrub(content)
    return {
        "role": role,
        "intent": classify_intent(clean, role),
        "outcome": classify_outcome(clean, role),
        "entities": extract_entities(clean),
        "chars": len(clean),
    }


def encode_session(messages: list[dict], platforms: list[str] | None = None) -> SessionSignal:
    signal = SessionSignal(platforms=list(platforms or []))
    for message in messages:
        signal.turns.append(encode_turn(message.get("role", ""), message.get("content", "")))
    return signal
