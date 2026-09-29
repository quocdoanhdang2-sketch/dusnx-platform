"""Authority boundary for personal-memory questions; no entity-specific rules."""
from __future__ import annotations
import re
import unicodedata


def _words(text: str) -> set[str]:
    stop = set("của tôi chúng ta bạn là và cho có gì nào này hiện tại nay dự án quyết định sử dụng rằng đã được không dùng chọn làm hệ thống chính hãy nhắc lại đang hiệu lực biết thông tin các về cả hai tất lưu nhớ muốn hỏi".split())
    return set(re.findall(r"\w+", unicodedata.normalize("NFC", text).casefold())) - stop


def select_memories(message: str, memories: list[dict], *, recall=False) -> list[dict]:
    """Select topic evidence, not recency. Call only after authorization/scope filtering.

    Shared words cannot disambiguate decisions. Multiple matches need an explicit
    conjunction/summary request; ties without one are deliberately unresolved.
    """
    if not memories:
        return []
    text=unicodedata.normalize("NFC",message).casefold()
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
    best=max(scores)
    chosen=[m for m,score in zip(memories,scores) if score==best]
    if best>0 and len(chosen)==1:
        return chosen
    # Generic recall with a single authoritative fact retains prior behavior.
    if recall and len(memories)==1:
        return memories
    return []


def is_memory_question(message: str) -> bool:
    text = message.casefold().strip()
    question = "?" in text or any(p in text for p in ("nhắc lại", "đã chọn gì", "đang dùng gì", "chọn gì", "dùng gì", "là gì", "nào"))
    personal = any(p in text for p in (
        "chọn", "quyết định", "lựa chọn", "dùng", "sử dụng",
        "hiện tại", "hiện nay", "dự án", "của tôi", "chúng tôi",
        "nhắc lại", "đã chốt", "thống nhất", "đã lưu", "ghi nhận",
        "tôi thích", "mục tiêu", "kế hoạch",
    ))
    return question and personal


def format_memory_answer(content: str) -> str:
    """Format memory answer without duplicate prefixes or doubled punctuation."""
    c = content.strip()
    prefix = "Theo trí nhớ đang hiệu lực:"
    if c.lower().startswith(prefix.lower()):
        c = c[len(prefix):].strip()
    c = re.sub(r"[.?!,;:]+$", "", c).strip()
    return f"{prefix} {c}."


def memory_answer_with_selection(message: str, memories: list[dict]) -> tuple[str | None, list[dict]]:
    """Return an attributed quotation and the matched memory dict.

    Retrieval has already enforced user/project/activity. Multiple unrelated
    candidates require clarification, not a fabricated single decision.
    """
    if not is_memory_question(message):
        return None, []
    selected=select_memories(message,memories,recall=True)
    if selected:
        return "\n".join(format_memory_answer(m["content"]) for m in selected), selected
    return "Tôi chưa đủ bối cảnh để chọn thông tin phù hợp. Bạn muốn hỏi về quyết định hoặc sở thích cụ thể nào?", []


def memory_answer_with_match(message: str, memories: list[dict]) -> tuple[str | None, dict | None]:
    """Compatibility wrapper for callers that expect a single match."""
    answer,selected=memory_answer_with_selection(message,memories)
    return answer, selected[0] if len(selected)==1 else None


def memory_answer(message: str, memories: list[dict]) -> str | None:
    ans, _ = memory_answer_with_match(message, memories)
    return ans
