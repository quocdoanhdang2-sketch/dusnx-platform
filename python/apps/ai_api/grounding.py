"""Authority boundary for personal-memory questions; no entity-specific rules."""
from __future__ import annotations
import re
import unicodedata


def _words(text: str) -> set[str]:
    stop = set("của tôi chúng ta bạn là và cho có gì nào này hiện tại nay quyết định sử dụng rằng đã được không dùng chọn làm hệ thống chính hãy nhắc lại đang hiệu lực biết thông tin các về cả hai tất lưu nhớ muốn hỏi".split())
    return set(re.findall(r"\w+", unicodedata.normalize("NFC", text).casefold())) - stop


def select_memories(message: str, memories: list[dict], *, recall=False) -> list[dict]:
    """Select topic evidence, not recency. Call only after authorization/scope filtering.

    Shared words cannot disambiguate decisions. Multiple matches need an explicit
    conjunction/summary request; ties without one are deliberately unresolved.
    """
    if not memories:
        return []
    text=unicodedata.normalize("NFC",message).casefold()

    # Intent-based routing for natural personal questions
    if recall or any(w in text for w in ("tôi", "mình", "của tôi")):
        if re.search(r"\b(?:tên\s+(?:tôi|mình)|tôi\s+tên|tôi\s+là\s+ai)\b", text):
            matches = [m for m in memories if any(k in m["content"].lower() for k in ("tên người dùng", "tên là", "người dùng là"))]
            if matches:
                return matches[:1]

        if re.search(r"\b(?:thuộc\s+ban|ở\s+ban|ban\s+nào|thành\s+viên\s+ban)\b", text):
            matches = [m for m in memories if "ban" in m["content"].lower()]
            if matches:
                return matches[:1]

        if re.search(r"\b(?:dự\s+án|đề\s+tài|đồ\s+án)\b", text):
            matches = [m for m in memories if any(k in m["content"].lower() for k in ("dự án", "đề tài", "đồ án"))]
            if matches:
                return matches[:1]

        if re.search(r"\b(?:thích|sở\s+thích|thường\s+dùng|hay\s+dùng)\b", text):
            matches = [m for m in memories if any(k in m["content"].lower() for k in ("thích", "sở thích", "ưu tiên", "thường dùng", "hay dùng")) or m.get("info_type") == "preference"]
            if matches:
                return matches[:1]

        if re.search(r"\b(?:mục\s+tiêu|kế\s+hoạch)\b", text):
            matches = [m for m in memories if any(k in m["content"].lower() for k in ("mục tiêu", "kế hoạch")) or m.get("info_type") == "goal"]
            if matches:
                return matches[:1]

    query=_words(text)
    words=[_words(m["content"]) for m in memories]
    shared=set.intersection(*words) if len(words)>1 else set()
    scores=[len(query & (w-shared)) for w in words]
    positive=[m for m,score in zip(memories,scores) if score>0]
    if recall and any(p in text for p in ("tất cả", "mọi quyết định")):
        return positive or (memories if not (query-{"mọi"}) else [])
    if recall and "cả hai" in text:
        return positive if len(positive)==2 else memories if len(memories)==2 else []
    if recall and re.search(r"\b(và|lẫn)\b",text) and len(positive)>1:
        return positive
    best=max(scores) if scores else 0
    chosen=[m for m,score in zip(memories,scores) if score==best]
    if best>0 and len(chosen)==1:
        return chosen
    # Generic recall with a single authoritative fact retains prior behavior.
    if recall and len(memories)==1:
        return memories
    return []


_TECHNICAL_SUBJECT = re.compile(
    r"(?i)\b(?:dusn[-\s]?x|model|mô\s*hình|checkpoint|gateway|api|rag|ollama|qwen|"
    r"provider|phiên\s*bản|version|kiến\s*trúc|mã\s*nguồn|code)\b"
)
_CLUB_SUBJECT = re.compile(
    r"(?i)\b(?:clb|câu\s*lạc\s*bộ|phòng\s*lab|lab\b|codefest|hackathon|ban\s*chủ\s*nhiệm|"
    r"chủ\s*nhiệm|phó\s*chủ\s*nhiệm|thành\s*viên|sinh\s*hoạt|workshop|team\s*building|"
    r"quy\s*chế|quy\s*định|nội\s*quy|quỹ|hội\s*phí|tài\s*chính|thu\s*chi|thủ\s*quỹ|"
    r"ngoại\s*lệ|mượn\s*phòng|trực\s*lab)\b"
)
_PERSONAL_ANCHOR = re.compile(
    r"(?i)\b(?:của\s+tôi|chúng\s+tôi|tôi\s+đã|đã\s+chốt|quyết\s+định(?:\s+của\s+tôi)?|"
    r"sở\s+thích(?:\s+của\s+tôi)?|tôi\s+chọn|tôi\s+thích|tôi\s+nghe|nhắc\s+lại\s+cho\s+tôi|"
    r"tôi\s+tên|tên\s+tôi|tôi\s+là\s+ai|tôi\s+ở\s+ban|tôi\s+thuộc\s+ban|ban\s+nào|"
    r"dự\s+án\s+của\s+tôi|đề\s+tài\s+của\s+tôi|mục\s+tiêu\s+của\s+tôi)\b"
)


def is_memory_question(message: str) -> bool:
    text = message.casefold().strip()
    # Translation/transform instructions can contain personal-memory vocabulary
    # and URL query markers. They are tasks over supplied text, not memory queries.
    if re.match(r"^(?:please\s+)?(?:translate|translation|dịch)\b", text):
        return False
    # Product/system questions ("DUSN-X dùng model nào?") and club questions share the verbs used
    # for personal decisions ("dùng", "nào", "sử dụng") but must reach documentation
    # retrieval, not the memory clarification path.
    if (_TECHNICAL_SUBJECT.search(text) or _CLUB_SUBJECT.search(text)) and not _PERSONAL_ANCHOR.search(text):
        return False
    question_text = re.sub(r"https?://\S+", " ", text)
    question = "?" in question_text or any(p in text for p in ("nhắc lại", "đã chọn gì", "đang dùng gì", "chọn gì", "dùng gì", "là gì", "nào", "được chọn", "là ai"))
    personal = any(p in text for p in (
        "chọn", "quyết định", "lựa chọn", "dùng", "sử dụng",
        "hiện tại", "hiện nay", "dự án", "đề tài", "của tôi", "chúng tôi",
        "nhắc lại", "đã chốt", "thống nhất", "đã lưu", "ghi nhận",
        "tôi thích", "sở thích", "mục tiêu", "kế hoạch", "công ty", "đồ uống", "công cụ",
        "tôi là ai", "tôi tên", "tên tôi", "tôi ở ban", "tôi thuộc", "ban nào",
    ))
    return question and personal


_PREFIXES = {
    "vi": "Theo trí nhớ đang hiệu lực:",
    "en": "From active memory:",
}
_CLARIFICATIONS = {
    "vi": "Tôi chưa đủ bối cảnh để chọn thông tin phù hợp. Bạn muốn hỏi về quyết định hoặc sở thích cụ thể nào?",
    "en": "I don't have enough context to choose a relevant memory. Which decision or preference would you like to ask about?",
}


def _reply_language(language: str | None) -> str:
    return language if language in _PREFIXES else "vi"


def format_memory_answer(content: str, language: str = "vi") -> str:
    """Format memory answer without duplicate prefixes or doubled punctuation."""
    language = _reply_language(language)
    c = content.strip()
    for existing in _PREFIXES.values():
        if c.casefold().startswith(existing.casefold()):
            c = c[len(existing):].strip()
            break
    c = re.sub(r"[.?!,;:]+$", "", c).strip()
    return f"{_PREFIXES[language]} {c}."


def memory_answer_with_selection(message: str, memories: list[dict], language: str = "vi") -> tuple[str | None, list[dict]]:
    """Return an attributed quotation and the matched memory dict.

    Retrieval has already enforced user/project/activity. The framing follows the
    saved response language; the quoted memory text is never translated.
    Multiple unrelated candidates require clarification, not a fabricated single
    decision.
    """
    language = _reply_language(language)
    if not is_memory_question(message):
        return None, []
    selected=select_memories(message,memories,recall=True)
    if selected:
        return "\n".join(format_memory_answer(m["content"], language) for m in selected), selected
    return _CLARIFICATIONS[language], []


def memory_answer_with_match(message: str, memories: list[dict], language: str = "vi") -> tuple[str | None, dict | None]:
    """Compatibility wrapper for callers that expect a single match."""
    answer,selected=memory_answer_with_selection(message,memories,language)
    return answer, selected[0] if len(selected)==1 else None


def memory_answer(message: str, memories: list[dict], language: str = "vi") -> str | None:
    ans, _ = memory_answer_with_match(message, memories, language)
    return ans
