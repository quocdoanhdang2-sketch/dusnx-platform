"""Authority boundary for personal-memory questions; no entity-specific rules."""
from __future__ import annotations
import re


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


def memory_answer_with_match(message: str, memories: list[dict]) -> tuple[str | None, Optional[dict]]:
    """Return an attributed quotation and the matched memory dict.

    Retrieval has already enforced user/project/activity. Multiple unrelated
    candidates require clarification, not a fabricated single decision.
    """
    if not is_memory_question(message) or not memories:
        return None, None
    if len(memories) == 1:
        return format_memory_answer(memories[0]["content"]), memories[0]
    stop = set("của tôi là và cho có gì nào này hiện tại dự án quyết định sử dụng rằng đã được không dùng".split())
    words = lambda text: set(re.findall(r"\w+", text.casefold())) - stop
    query = words(message)
    scored = [(len(query & words(m["content"])), m) for m in memories]
    best = max(score for score, _ in scored)
    candidates = [m for score, m in scored if score == best]
    if best > 0 and len(candidates) == 1:
        return format_memory_answer(candidates[0]["content"]), candidates[0]
    return "Có nhiều thông tin đang hiệu lực. Bạn muốn hỏi về quyết định hoặc sở thích cụ thể nào?", None


def memory_answer(message: str, memories: list[dict]) -> str | None:
    ans, _ = memory_answer_with_match(message, memories)
    return ans
