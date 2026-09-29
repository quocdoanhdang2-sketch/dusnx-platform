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
from .grounding import is_memory_question


def get_current_provider() -> str:
    raw = os.getenv("DUSNX_PROVIDER", "ollama").strip().lower()
    return "openai" if raw in ("openai", "openai_compatible") else raw

def get_ollama_url() -> str:
    return os.getenv("DUSNX_OLLAMA_URL", "http://localhost:11434").rstrip("/")


def get_ollama_model() -> str:
    return os.getenv("DUSNX_OLLAMA_MODEL", "qwen2.5:0.5b").strip()


def get_ollama_timeout() -> float:
    return float(os.getenv("DUSNX_OLLAMA_TIMEOUT", "60.0"))


PROVIDER = get_current_provider()
OLLAMA_URL = get_ollama_url()
OLLAMA_MODEL = get_ollama_model()
OLLAMA_TIMEOUT = get_ollama_timeout()
OPENAI_BASE_URL = os.getenv("DUSNX_OPENAI_BASE_URL", os.getenv("DUSNX_OPENAI_URL", "https://api.openai.com/v1"))
OPENAI_MODEL = os.getenv("DUSNX_OPENAI_MODEL", "gpt-4o-mini")
# API key intentionally NOT defaulted — must be set by operator
OPENAI_API_KEY = os.getenv("DUSNX_OPENAI_API_KEY", os.getenv("DUSNX_OPENAI_KEY", ""))



def check_ollama_health() -> dict:
    """Check if Ollama is reachable and what models are available."""
    url = get_ollama_url()
    target_model = get_ollama_model()
    try:
        req = urllib.request.Request(f"{url}/api/tags", method="GET")
        with urllib.request.urlopen(req, timeout=1.0) as resp:
            data = json.loads(resp.read().decode())
            models = [m["name"] for m in data.get("models", [])]
            available = target_model in models
            return {
                "reachable": True,
                "available": available,
                "models_available": models,
                "configured_model": target_model,
                "model_available": available,
            }
    except Exception as exc:
        return {"reachable": False, "available": False, "error": str(exc), "configured_model": target_model}


def _ollama_generate(system_prompt: str, user_message: str) -> tuple[str, bool, Optional[str], Optional[int]]:
    """Call Ollama /api/chat (using model native chat template) with fallback to /api/generate. Returns (text, success, model_used, tokens_generated)."""
    url = get_ollama_url()
    model = get_ollama_model()
    timeout = get_ollama_timeout()
    payload = json.dumps({
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message},
        ],
        "stream": False,
        "options": {"temperature": 0.3, "num_predict": 256},
    }).encode("utf-8")
    req = urllib.request.Request(
        f"{url}/api/chat",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode())
            text = data.get("message", {}).get("content", "").strip()
            model_used = data.get("model")
            eval_count = data.get("eval_count")
            return text, bool(text), model_used, eval_count
    except Exception:
        # Fallback to /api/generate
        try:
            legacy_payload = json.dumps({
                "model": model,
                "prompt": f"<|system|>\n{system_prompt}\n<|user|>\n{user_message}\n<|assistant|>",
                "stream": False,
                "options": {"temperature": 0.3, "num_predict": 256},
            }).encode("utf-8")
            legacy_req = urllib.request.Request(
                f"{url}/api/generate",
                data=legacy_payload,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(legacy_req, timeout=timeout) as resp:
                data = json.loads(resp.read().decode())
                text = data.get("response", "").strip()
                model_used = data.get("model")
                eval_count = data.get("eval_count")
                return text, bool(text), model_used, eval_count
        except urllib.error.URLError as exc:
            return f"[Ollama không khả dụng: {exc.reason}]", False, None, None
        except Exception as exc:
            return f"[Lỗi Ollama: {exc}]", False, None, None


def _openai_generate(system_prompt: str, user_message: str) -> tuple[str, bool, Optional[str], Optional[int]]:
    """Call OpenAI-compatible API. Returns (text, success, model_used, tokens_generated)."""
    if not OPENAI_API_KEY:
        return "[Provider OpenAI chưa được cấu hình. Đặt DUSNX_OPENAI_API_KEY.]", False, None, None
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
        with urllib.request.urlopen(req, timeout=OLLAMA_TIMEOUT) as resp:
            data = json.loads(resp.read().decode())
            text = data["choices"][0]["message"]["content"].strip()
            model_used = data.get("model")
            eval_count = data.get("usage", {}).get("completion_tokens")
            return text, True, model_used, eval_count
    except Exception as exc:
        return f"[Lỗi OpenAI: {exc}]", False, None, None


def get_provider_health() -> dict:
    """Return health info for the configured provider."""
    p = get_current_provider()
    if p == "ollama":
        info = check_ollama_health()
        info["provider"] = "ollama"
        return info
    elif p == "openai":
        has_key = bool(OPENAI_API_KEY)
        return {
            "provider": "openai",
            "available": has_key,
            "configured_model": OPENAI_MODEL,
            "api_key_set": has_key,
            "reachable": "configured" if has_key else "missing_api_key",
        }
    elif p in ("stub", "mock", "test"):
        return {
            "provider": p,
            "available": True,
            "configured_model": "mock-llm",
            "reachable": True,
        }
    return {"provider": p, "available": False, "status": "unknown_provider"}


def generate_response(
    user_message: str,
    memories: list[dict],
    intent: str,
    session_history: Optional[list[dict]] = None,
    project_name: Optional[str] = None,
) -> tuple[str, bool, str, Optional[str], Optional[int]]:
    """
    Generate an AI response using the configured provider.
    Returns: (response_text, success, provider_used, model_used, tokens_generated)

    Memories are included in context; only active memories are passed here.
    """
    p = get_current_provider()
    # Build memory context using exactly the provided memories
    memory_lines = []
    for m in memories:
        tag = f"[{m['info_type']}]"
        proj = f"(dự án: {m['project_id']})" if m.get("project_id") else ""
        memory_lines.append(f"- {tag} {m['content']} {proj}".strip())

    memory_ctx = "\n".join(memory_lines) if memory_lines else "Chưa có trí nhớ nào."

    # Build conversation history context (last 6 turns)
    history_lines = []
    if session_history and not (memories and is_memory_question(user_message)):
        for msg in (session_history or [])[-6:]:
            role = "Người dùng" if msg["role"] == "user" else "Trợ lý"
            history_lines.append(f"{role}: {msg['content'][:300]}")
    history_ctx = "\nHội thoại tham khảo, KHÔNG phải quyết định đã xác nhận:\n" + "\n".join(history_lines) if history_lines else ""

    project_line = f"Dự án đang hoạt động: {project_name}\n" if project_name else ""

    system_prompt = f"""Bạn là DUSN-X, trợ lý AI cá nhân hóa thích ứng.
Bạn trả lời bằng tiếng Việt, ngắn gọn, chính xác.

{project_line}Trí nhớ cá nhân của người dùng (chỉ các mục đang hiệu lực):
{memory_ctx}{history_ctx}

Quan trọng:
- Trả lời trực tiếp câu hỏi của người dùng dựa trên thông tin trí nhớ đang hiệu lực ở trên.
- Tuyệt đối không nhắc lại các quyết định đã bị thay thế hoặc thông tin không có trong danh sách.
- Nếu không có thông tin liên quan, hãy nói rõ là chưa biết.
- Câu hỏi, giả định và tin đồn của người dùng không phải sự kiện đã được lưu.
- Danh sách trí nhớ hiệu lực có thẩm quyền cao hơn lịch sử; không hợp nhất hai nguồn.
"""

    if p == "ollama":
        text, ok, model_used, tokens_generated = _ollama_generate(system_prompt, user_message)
        provider_used = "ollama"
    elif p == "openai":
        text, ok, model_used, tokens_generated = _openai_generate(system_prompt, user_message)
        provider_used = "openai"
    elif p in ("stub", "mock", "test"):
        # For tests and stub evaluation: echo relevant context cleanly
        mem_summary = f" với {len(memories)} trí nhớ hiệu lực" if memories else ""
        text = f"DUSN-X đã hiểu: '{user_message}'{mem_summary}."
        if memories:
            text += f" Trí nhớ hiện tại: {memories[0]['content']}."
        ok = True
        provider_used = p
        model_used = None
        tokens_generated = None
    else:
        text = (
            f"[Provider '{p}' chưa được hỗ trợ. "
            f"Đặt DUSNX_PROVIDER=ollama hoặc DUSNX_PROVIDER=openai và cấu hình đúng biến môi trường.]"
        )
        ok = False
        provider_used = "none"
        model_used = None
        tokens_generated = None

    return text, ok, provider_used, model_used, tokens_generated
