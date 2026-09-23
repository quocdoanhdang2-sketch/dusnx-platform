from __future__ import annotations

from dataclasses import dataclass
import re


@dataclass(frozen=True)
class RouteDecision:
    intent: str
    agent: str
    next_action: str
    confidence: float


# High-precision product commands. These rules do not replace the learned model;
# they constrain only explicit commands whose business meaning is unambiguous.
_RULES = (
    (
        re.compile(r"\b(tạo|làm|soạn|chuyển|biến|rút chữ)\b.{0,60}\b(slide|powerpoint|trình chiếu)\b", re.I),
        RouteDecision("presentation_edit", "productivity", "edit_slide", 0.98),
    ),
    (
        re.compile(r"\b(tóm tắt|rút gọn|ý chính|tổng hợp)\b", re.I),
        RouteDecision("summarize", "productivity", "summarize", 0.97),
    ),
    (
        re.compile(r"\b(tiếp tục|làm tiếp|hôm trước|vừa rồi|continue)\b", re.I),
        RouteDecision("followup", "conversation", "clarify", 0.94),
    ),
    (
        re.compile(r"\b(gợi ý|đề xuất|khuyên|recommend)\b", re.I),
        RouteDecision("recommendation", "conversation", "recommend", 0.95),
    ),
    (
        re.compile(r"\b(tìm|tra cứu|nghiên cứu|phân tích|search|research)\b", re.I),
        RouteDecision("research", "search_rag", "search", 0.96),
    ),
)


def match_explicit_route(platform: str, content: str) -> RouteDecision | None:
    text = (content or "").casefold().strip()
    if not text:
        return None

    # PowerPoint requests often omit the word "slide" because the host application
    # already supplies that context.
    if platform.casefold() == "powerpoint" and re.search(r"\b(tạo|làm|soạn|chuyển|biến)\b", text):
        return RouteDecision("presentation_edit", "productivity", "edit_slide", 0.98)

    for pattern, decision in _RULES:
        if pattern.search(text):
            return decision
    return None
