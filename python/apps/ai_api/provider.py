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
import socket
from typing import Optional
import urllib.request
import urllib.error
from .grounding import is_memory_question


class ProviderResult(tuple):
    """Backward-compatible five values plus per-invocation transport metadata."""
    def __new__(cls, text, ok, provider, model, tokens, *, called=False):
        result=super().__new__(cls,(text,ok,provider,model,tokens))
        result.provider_called=called
        return result


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
            if not isinstance(data, dict) or not isinstance(data.get("models"), list):
                raise ValueError("invalid_schema")
            models = [m["name"] for m in data["models"] if isinstance(m, dict) and isinstance(m.get("name"), str)]
            available = target_model in models
            return {
                "reachable": True,
                "available": available,
                "models_available": models,
                "configured_model": target_model,
                "model_available": available,
            }
    except Exception as exc:
        return {"reachable": False, "available": False, "error": ollama_error(exc), "model_available": False, "configured_model": target_model}


def validate_ollama_response(data: object) -> tuple[str, str, Optional[int]]:
    """Require a completed native chat response; reject partial or malformed output."""
    if not isinstance(data, dict) or data.get("done") is not True:
        raise ValueError("invalid_schema")
    message = data.get("message")
    model = data.get("model")
    if not isinstance(message, dict) or not isinstance(message.get("content"), str):
        raise ValueError("invalid_schema")
    text = message["content"].strip()
    if not text or not isinstance(model, str) or not model.strip():
        raise ValueError("invalid_schema")
    tokens = data.get("eval_count")
    if tokens is not None and (type(tokens) is not int or tokens < 0):
        raise ValueError("invalid_schema")
    return text, model, tokens


def ollama_error(exc: Exception) -> str:
    # Stable categories only: never return URL, payload, headers or exception text.
    if isinstance(exc, urllib.error.HTTPError):
        return "model_missing" if exc.code == 404 else f"http_{exc.code}"
    if isinstance(exc, json.JSONDecodeError):
        return "invalid_json"
    if isinstance(exc, ValueError):
        return "invalid_schema"
    if isinstance(exc, (TimeoutError, socket.timeout)):
        return "timeout"
    if isinstance(exc, urllib.error.URLError):
        return "unreachable"
    return "transport_error"


def _ollama_generate(system_prompt: str, user_message: str) -> tuple[str, bool, Optional[str], Optional[int]]:
    """One native chat attempt. Transport failure must never become a successful reply."""
    payload = json.dumps({
        "model": get_ollama_model(),
        "messages": [{"role": "system", "content": system_prompt},
                     {"role": "user", "content": user_message}],
        "stream": False, "options": {"temperature": 0.3, "num_predict": 256},
    }).encode("utf-8")
    request = urllib.request.Request(get_ollama_url() + "/api/chat", data=payload,
                                     headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=get_ollama_timeout()) as response:
            data = json.load(response)
        text, model, tokens = validate_ollama_response(data)
        return text, True, model, tokens
    except Exception as exc:
        category = ollama_error(exc)
        descriptions = {"model_missing": "Model cấu hình không tồn tại trong Ollama",
                        "unreachable": "Không kết nối được Ollama", "timeout": "Ollama quá thời gian chờ",
                        "invalid_json": "Ollama trả dữ liệu không phải JSON",
                        "invalid_schema": "Ollama trả JSON không đúng hợp đồng"}
        return f"[{descriptions.get(category, 'Lỗi dịch vụ Ollama')} ({category})]", False, None, None


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
        return f"[Lỗi OpenAI ({ollama_error(exc)})]", False, None, None


def get_provider_health() -> dict:
    """Return health info for the configured provider."""
    p = get_current_provider()
    if p == "ollama":
        info = check_ollama_health()
        info["provider"] = "ollama"
        return info
    elif p == "openai":
        has_key = bool(OPENAI_API_KEY)
        info = {
            "provider": "openai",
            "available": False,
            "configured_model": OPENAI_MODEL,
            "api_key_set": has_key,
            "reachable": False,
            "model_available": False,
        }
        if not has_key:
            info["error"] = "missing_api_key"
            return info
        try:
            request = urllib.request.Request(OPENAI_BASE_URL.rstrip("/") + "/models",
                                             headers={"Authorization": "Bearer " + OPENAI_API_KEY})
            with urllib.request.urlopen(request, timeout=1.0) as response:
                data = json.load(response)
            if not isinstance(data, dict) or not isinstance(data.get("data"), list):
                raise ValueError("invalid_schema")
            models = [m.get("id") for m in data["data"] if isinstance(m, dict)]
            info.update(reachable=True, available=OPENAI_MODEL in models, model_available=OPENAI_MODEL in models)
        except Exception as exc:
            info["error"] = ollama_error(exc)
        return info
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
    response_language: str = "vi",
) -> tuple[str, bool, str, Optional[str], Optional[int]]:
    """
    Generate an AI response using the configured provider.
    Returns: (response_text, success, provider_used, model_used, tokens_generated)

    Memories are included in context; only active memories are passed here.
    """
    p = get_current_provider()
    # Build memory context using exactly the provided memories
    called = False
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

    language_rule = ("Reply in English, concisely and accurately. Preserve names, IDs, URLs and code verbatim."
                     if response_language == "en" else
                     "Bạn trả lời bằng tiếng Việt, ngắn gọn, chính xác. Giữ nguyên tên riêng, ID, URL và code.")
    system_prompt = f"""Bạn là DUSN-X, trợ lý AI cá nhân hóa thích ứng.
{language_rule}

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
        called = True  # _ollama_generate attempts the HTTP transport, including failures.
        provider_used = "ollama"
    elif p == "openai":
        text, ok, model_used, tokens_generated = _openai_generate(system_prompt, user_message)
        called = bool(OPENAI_API_KEY)  # Missing configuration returns before any HTTP attempt.
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

    return ProviderResult(text, ok, provider_used, model_used, tokens_generated, called=called)
