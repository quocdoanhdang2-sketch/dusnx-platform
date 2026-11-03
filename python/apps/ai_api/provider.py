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
import re
import socket
from typing import Optional
import urllib.request
import urllib.error
from .grounding import is_memory_question
from .language import detect_language


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


def _ollama_model_tag_matches(configured: str, available: str) -> bool:
    """Treat an untagged model name as Ollama's implicit ``:latest`` tag only."""
    return configured == available or (":" not in configured and available == configured + ":latest")


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
            available = any(_ollama_model_tag_matches(target_model, name) for name in models)
            health = {
                "reachable": True,
                "available": available,
                "models_available": models,
                "configured_model": target_model,
                "model_available": available,
            }
            if not available:
                health["error"] = "model_missing"
            return health
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
    repeat_penalty = float(os.getenv("DUSNX_OLLAMA_REPEAT_PENALTY", "1.25"))
    repeat_last_n = int(os.getenv("DUSNX_OLLAMA_REPEAT_LAST_N", "64"))
    temperature = float(os.getenv("DUSNX_OLLAMA_TEMPERATURE", "0.1"))
    payload = json.dumps({
        "model": get_ollama_model(),
        "messages": [{"role": "system", "content": system_prompt},
                     {"role": "user", "content": user_message}],
        "stream": False,
        "options": {
            "temperature": temperature,
            "num_predict": 256,
            "repeat_penalty": repeat_penalty,
            "repeat_last_n": repeat_last_n,
        },
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


def clean_url(u: str) -> str:
    """Strip trailing punctuation that is not part of the URL."""
    return re.sub(r"[.,;!?:)'\"]+$", "", u)


def sanitize_generated_reply(text: str) -> str:
    """Strip accidental leakage of system instructions or prompt boilerplate from model output."""
    if not text:
        return ""
    cleaned = text.strip()
    patterns = [
        r"^(?:Quan trọng|BẮT BUỘC|Chỉ thị hệ thống|Quy tắc|Rules|Instructions|CRITICAL MANDATORY INSTRUCTION):\s*",
        r"^(?:Trả lời thẳng vào câu hỏi|Trả lời trực tiếp câu hỏi)[^\n]*\n*",
    ]
    for pat in patterns:
        cleaned = re.sub(pat, "", cleaned, flags=re.IGNORECASE).strip()
    return cleaned


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

    query_lang = detect_language(user_message)

    if response_language == "en":
        project_line_en = f"Active project: {project_name}\n" if project_name else ""
        mem_lines = [f"- [{m.get('info_type', 'info')}] {m.get('content', '')}" for m in memories]
        mem_ctx_en = "\n".join(mem_lines) if mem_lines else "No active memories."
        hist_lines_en = []
        if session_history and not (memories and is_memory_question(user_message)):
            for msg in (session_history or [])[-6:]:
                role = "User" if msg["role"] == "user" else "Assistant"
                hist_lines_en.append(f"{role}: {msg['content'][:300]}")
        hist_ctx_en = "\nConversation history for reference (NOT confirmed decisions):\n" + "\n".join(hist_lines_en) if hist_lines_en else ""

        system_prompt = f"""You are DUSN-X, an adaptive personalized AI assistant.
CRITICAL MANDATORY INSTRUCTION: You MUST write your ENTIRE response in ENGLISH ONLY.
Even if the user message is in Vietnamese or another language, translate and answer strictly in English. Do NOT write any Vietnamese words.
Preserve proper names, IDs, URLs, and code verbatim.

System Information:
- DUSN-X is an adaptive personalized AI assistant platform featuring: long-term memory management (persisting and superseding user decisions), multi-agent intent routing, data analysis, and Web/Office taskpane integration.

{project_line_en}Active user memories:
{mem_ctx_en}{hist_ctx_en}

Rules:
- Answer directly and concisely in English.
- Do NOT repeat sentences or lines.
- Never mention superseded decisions.
- If information is not known, state that clearly in English.
"""
        raw_urls = re.findall(r"https?://[^\s\"'>)]+", user_message)
        urls = [clean_url(u) for u in raw_urls if clean_url(u)]
        vars_kv = re.findall(r"\b[A-Za-z0-9_]+=[A-Za-z0-9_.:/-]+", user_message)

        is_url_fetch = bool(urls and re.search(r"(?:tóm tắt|đọc|nội dung|phân tích|summarize|read|content of)\b", user_message, re.I))

        if is_url_fetch:
            llm_user_message = (
                f"Instruction: DUSN-X does not have internet access to fetch external URL content ({urls[0]}). "
                f"State this limitation clearly and ask the user to provide the article text.\n\n"
                f"User request: {user_message}"
            )
        elif urls or vars_kv:
            directives = []
            if urls:
                directives.append(f"URL: {', '.join(urls)}")
            if vars_kv:
                directives.append(f"Variables: {', '.join(vars_kv)}")
            prefix = "Instruction: Fulfill the user request while preserving these exact entities verbatim:\n- " + "\n- ".join(directives)
            llm_user_message = f"{prefix}\n\nRequest: {user_message}\n\nAnswer in English:"
        elif query_lang == "vi":
            llm_user_message = f"Translate and answer the following question strictly in English (use 'and', never 'và'): '{user_message}'. Answer in English:"
        else:
            llm_user_message = user_message
    else:
        project_line = f"Dự án đang hoạt động: {project_name}\n" if project_name else ""
        system_prompt = f"""Bạn là DUSN-X, hệ thống trợ lý AI cá nhân hóa thích ứng. Trả lời bằng tiếng Việt ngắn gọn, hữu ích.
Giữ nguyên tên riêng, ID, URL và mã code nếu có.

Thông tin hệ thống DUSN-X:
- DUSN-X là hệ thống trợ lý AI cá nhân hóa thích ứng với các tính năng cốt lõi: 1) Quản lý trí nhớ dài hạn (ghi nhớ và cập nhật quyết định cá nhân); 2) Định tuyến tác vụ qua router đa tác tử; 3) Phân tích dữ liệu; 4) Tích hợp giao diện Web và Office taskpane.

{project_line}Trí nhớ hiệu lực:
{memory_ctx}{history_ctx}
"""
        raw_urls = re.findall(r"https?://[^\s\"'>)]+", user_message)
        urls = [clean_url(u) for u in raw_urls if clean_url(u)]
        vars_kv = re.findall(r"\b[A-Za-z0-9_]+=[A-Za-z0-9_.:/-]+", user_message)

        is_url_fetch = bool(urls and re.search(r"(?:tóm tắt|đọc|nội dung|phân tích|summarize|read|content of)\b", user_message, re.I))

        if is_url_fetch:
            llm_user_message = (
                f"Chỉ dẫn: DUSN-X hiện chưa có tính năng duyệt web để đọc trực tiếp URL ngoài ({urls[0]}). "
                f"Hãy nêu rõ giới hạn này và yêu cầu người dùng gửi trực tiếp nội dung văn bản để xử lý.\n\n"
                f"Yêu cầu của người dùng: {user_message}"
            )
        elif urls or vars_kv:
            directives = []
            if urls:
                directives.append(f"URL: {', '.join(urls)}")
            if vars_kv:
                directives.append(f"Biến: {', '.join(vars_kv)}")
            prefix = "Yêu cầu: Trả lời bằng câu hoàn chỉnh tiếng Việt và ghi đúng nguyên văn các mục sau:\n- " + "\n- ".join(directives)
            llm_user_message = f"{prefix}\n\nCâu hỏi: {user_message}\n\nTrả lời bằng tiếng Việt:"
        elif query_lang == "en":
            llm_user_message = f"Dịch và trả lời câu hỏi sau hoàn toàn bằng TIẾNG VIỆT (dùng 'và', không dùng từ tiếng Anh): '{user_message}'. Trả lời bằng tiếng Việt:"
        else:
            llm_user_message = user_message

    if p == "ollama":
        text, ok, model_used, tokens_generated = _ollama_generate(system_prompt, llm_user_message)
        called = True  # _ollama_generate attempts the HTTP transport, including failures.
        provider_used = "ollama"
        if ok:
            text = sanitize_generated_reply(text)
    elif p == "openai":
        text, ok, model_used, tokens_generated = _openai_generate(system_prompt, llm_user_message)
        called = bool(OPENAI_API_KEY)  # Missing configuration returns before any HTTP attempt.
        provider_used = "openai"
        if ok:
            text = sanitize_generated_reply(text)
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

    # Sanitization can remove the entire response after transport validation.
    # Preserve that a call happened, but never save an empty reply as success.
    if ok and not text.strip():
        text = "[Provider trả về nội dung rỗng sau xử lý (empty_response)]"
        ok = False
        model_used = tokens_generated = None

    return ProviderResult(text, ok, provider_used, model_used, tokens_generated, called=called)
