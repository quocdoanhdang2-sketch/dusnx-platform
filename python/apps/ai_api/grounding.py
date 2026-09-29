"""Authority boundary for personal-memory questions; no entity-specific rules."""
from __future__ import annotations
import re


def is_memory_question(message: str) -> bool:
    text = message.casefold().strip()
    question = "?" in text or any(p in text for p in ("nhắc lại", "đã chọn gì", "đang dùng gì"))
    personal = any(p in text for p in (
        "hiện tại", "dự án", "đã chọn", "đã chốt", "đã lưu", "ghi nhận", "tôi thích", "của tôi",
        "nhắc lại", "đang dùng", "quyết định", "lựa chọn", "mục tiêu",
    ))
    return question and personal


def memory_answer(message: str, memories: list[dict]) -> str | None:
    """Return an attributed quotation, never promote a question into a fact.

    Retrieval has already enforced user/project/activity. Multiple unrelated
    candidates require clarification, not a fabricated single decision.
    """
    if not is_memory_question(message) or not memories:
        return None
    if len(memories) == 1:
        return f"Theo trí nhớ đang hiệu lực: {memories[0]['content']}."
    stop = set("của tôi là và cho có gì nào này hiện tại dự án quyết định sử dụng rằng đã được không dùng".split())
    words = lambda text: set(re.findall(r"\w+", text.casefold())) - stop
    query = words(message)
    scored = [(len(query & words(m["content"])), m) for m in memories]
    best = max(score for score, _ in scored)
    candidates = [m for score, m in scored if score == best]
    if best > 0 and len(candidates) == 1:
        return f"Theo trí nhớ đang hiệu lực: {candidates[0]['content']}."
    return "Có nhiều thông tin đang hiệu lực. Bạn muốn hỏi về quyết định hoặc sở thích cụ thể nào?"
