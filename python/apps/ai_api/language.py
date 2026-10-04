"""Deterministic Vietnamese/English policy used before any LLM call."""
from __future__ import annotations

import re
import unicodedata

SUPPORTED = {"auto", "vi", "en"}
VI_WORDS = {"bạn", "tôi", "mình", "là", "và", "không", "có", "hãy", "đang", "đã", "muốn", "trả", "lời", "bằng", "tiếng"}
EN_WORDS = {"the", "is", "are", "you", "please", "what", "which", "how", "answer", "english", "vietnamese", "from", "now"}
VI_DIACRITICS = re.compile(r"[ăâđêôơưáàảãạấầẩẫậắằẳẵặéèẻẽẹếềểễệíìỉĩịóòỏõọốồổỗộớờởỡợúùủũụứừửữựýỳỷỹỵ]", re.I)


def detect_language(text: str, previous: str | None = None) -> str:
    normalized = unicodedata.normalize("NFC", text).casefold()
    words = set(re.findall(r"[\w]+", normalized, flags=re.UNICODE))
    if len(normalized.strip()) <= 5 and previous in {"vi", "en"}:
        return previous
    vi = len(VI_DIACRITICS.findall(normalized)) * 2 + len(words & VI_WORDS)
    en = len(words & EN_WORDS)
    if vi > en and vi:
        return "vi"
    if en > vi and en:
        return "en"
    return "unknown"


def response_language(preference: str, detected: str, previous: str | None = None) -> str:
    preference = preference if preference in SUPPORTED else "auto"
    if preference in {"vi", "en"}:
        return preference
    if detected in {"vi", "en"}:
        return detected
    return previous if previous in {"vi", "en"} else "vi"


def preference_instruction(text: str) -> str | None:
    value = unicodedata.normalize("NFC", text).casefold().strip()
    if re.search(r"(?:từ giờ|kể từ giờ).*(?:tiếng anh|english)|answer in english from now on", value):
        return "en"
    if re.search(r"(?:từ giờ|kể từ giờ).*(?:tiếng việt|vietnamese)|answer in vietnamese from now on", value):
        return "vi"
    return None
