"""
DUSN-X Text Generation Provider
- Abstraction layer for LLM providers
- Priority: local Ollama → stub response (transparent about capability)
- Provider is configured via DUSNX_PROVIDER env var
- API keys NEVER in source code
"""
from __future__ import annotations

import json
import os
from typing import Optional
import urllib.request
import urllib.error


PROVIDER = os.getenv("DUSNX_PROVIDER", "ollama")
OLLAMA_URL = os.getenv("DUSNX_OLLAMA_URL", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("DUSNX_OLLAMA_MODEL", "llama3.2")
OPENAI_BASE_URL = os.getenv("DUSNX_OPENAI_BASE_URL", "https://api.openai.com/v1")
OPENAI_MODEL = os.getenv("DUSNX_OPENAI_MODEL", "gpt-4o-mini")
# API key intentionally NOT defaulted — must be set by operator
OPENAI_API_KEY = os.getenv("DUSNX_OPENAI_API_KEY", "")


def check_ollama_health() -> dict:
    """Check if Ollama is reachable and what models are available."""
    try:
        req = urllib.request.Request(f"{OLLAMA_URL}/api/tags", method="GET")
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode())
            models = [m["name"] for m in data.get("models", [])]
            available = OLLAMA_MODEL in models or any(OLLAMA_MODEL.split(":")[0] in m for m in models)
            return {
                "reachable": True,
                "models_available": models,
                "configured_model": OLLAMA_MODEL,
                "model_available": available,
            }
    except Exception as exc:
        return {"reachable": False, "error": str(exc), "configured_model": OLLAMA_MODEL}


def _ollama_generate(system_prompt: str, user_message: str) -> tuple[str, bool]:
    """Call Ollama /api/generate. Returns (text, success)."""
    payload = json.dumps({
        "model": OLLAMA_MODEL,
        "prompt": f"<|system|>\n{system_prompt}\n<|user|>\n{user_message}\n<|assistant|>",
        "stream": False,
        "options": {"temperature": 0.7, "num_predict": 1024},
    }).encode("utf-8")
    req = urllib.request.Request(
        f"{OLLAMA_URL}/api/generate",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            data = json.loads(resp.read().decode())
            return data.get("response", ""), True
    except urllib.error.URLError as exc:
        return f"[Ollama không khả dụng: {exc.reason}]", False
    except Exception as exc:
        return f"[Lỗi Ollama: {exc}]", False


def _openai_generate(system_prompt: str, user_message: str) -> tuple[str, bool]:
    """Call OpenAI-compatible API. Returns (text, success)."""
    if not OPENAI_API_KEY:
        return "[Provider OpenAI chưa được cấu hình. Đặt DUSNX_OPENAI_API_KEY.]", False
    payload = json.dumps({
        "model": OPENAI_MODEL,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message},
        ],
        "temperature": 0.7,
        "max_tokens": 1024,
    }).encode("utf-8")
    req = urllib.request.Request(
        f"{OPENAI_BASE_URL}/chat/completions",
        data=payload,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {OPENAI_API_KEY}",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            data = json.loads(resp.read().decode())
            return data["choices"][0]["message"]["content"], True
    except Exception as exc:
        return f"[Lỗi OpenAI: {exc}]", False


def get_provider_health() -> dict:
    """Return health info for the configured provider."""
    if PROVIDER == "ollama":
        info = check_ollama_health()
        info["provider"] = "ollama"
        return info
    elif PROVIDER == "openai":
        return {
            "provider": "openai",
            "configured_model": OPENAI_MODEL,
            "api_key_set": bool(OPENAI_API_KEY),
            "reachable": "unknown — not checked at startup",
        }
    return {"provider": PROVIDER, "status": "unknown_provider"}


def generate_response(
    user_message: str,
    memories: list[dict],
    intent: str,
    session_history: Optional[list[dict]] = None,
    project_name: Optional[str] = None,
) -> tuple[str, bool, str]:
    """
    Generate an AI response using the configured provider.
    Returns: (response_text, success, provider_used)

    Memories are included in context; only active memories are passed here.
    """
    # Build memory context
    memory_lines = []
    for m in memories[:15]:  # cap at 15 items to keep context manageable
        tag = f"[{m['info_type']}]"
        proj = f"(dự án: {m['project_id']})" if m.get("project_id") else ""
        memory_lines.append(f"- {tag} {m['content']} {proj}".strip())

    memory_ctx = "\n".join(memory_lines) if memory_lines else "Chưa có trí nhớ nào."

    # Build conversation history context (last 6 turns)
    history_lines = []
    if session_history:
        for msg in (session_history or [])[-6:]:
            role = "Người dùng" if msg["role"] == "user" else "Trợ lý"
            history_lines.append(f"{role}: {msg['content'][:300]}")
    history_ctx = "\n".join(history_lines) if history_lines else ""

    project_line = f"Dự án đang hoạt động: {project_name}\n" if project_name else ""

    system_prompt = f"""Bạn là DUSN-X, trợ lý AI cá nhân hóa thích ứng.
Bạn trả lời bằng tiếng Việt, ngắn gọn, chính xác.

{project_line}Trí nhớ cá nhân của người dùng (chỉ các mục đang hiệu lực):
{memory_ctx}

Lịch sử hội thoại gần đây:
{history_ctx}

Quan trọng:
- Chỉ sử dụng thông tin trong trí nhớ khi nó thực sự liên quan đến câu hỏi.
- Nếu không có thông tin liên quan, hãy nói rõ là chưa biết và hỏi lại người dùng.
- Không tự tạo ra "ký ức" không có trong danh sách.
- Intent hiện tại được phân loại là: {intent}
"""

    if PROVIDER == "ollama":
        text, ok = _ollama_generate(system_prompt, user_message)
        provider_used = "ollama"
    elif PROVIDER == "openai":
        text, ok = _openai_generate(system_prompt, user_message)
        provider_used = "openai"
    else:
        text = (
            f"[Provider '{PROVIDER}' chưa được hỗ trợ. "
            f"Đặt DUSNX_PROVIDER=ollama hoặc DUSNX_PROVIDER=openai và cấu hình đúng biến môi trường.]"
        )
        ok = False
        provider_used = "none"

    return text, ok, provider_used
