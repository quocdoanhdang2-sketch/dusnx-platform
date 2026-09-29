"""
DUSN-X Decision Updater & Memory Quality Module
- Extracts modification components (topic, new_value, target) from user utterances
- Synthesizes full, grammatically complete updated decision sentences preserving subject, predicate, and scope
- Resolves target decision ambiguity when multiple active decisions exist
- Strictly general: works on any domain, entity, or tech stack without hardcoded rules
"""
from __future__ import annotations

import re
import unicodedata
from typing import Optional


# Vietnamese polite and modal particles to strip from values
_POLITE_PARTICLES_PATTERN = re.compile(
    r"(?i)(?:\s+(?:nhé|nha|nhe|nhá|ạ|đi|nhỉ|với|ngay|nào|giúp\s+tôi|giúp|với\s+ạ))+\s*[.?!]*$"
)

# Common verb prefixes in Vietnamese modify requests
_MODIFY_PREFIX_PATTERN = re.compile(
    r"(?i)^(?:hãy\s+)?(?:đổi|thay\s+đổi|thay|chuyển|cập\s+nhật|chọn|sửa|điều\s+chỉnh)\s+(?:lại\s+)?(?:quyết\s+định|lựa\s+chọn|kế\s+hoạch|mục\s+tiêu)?\s*"
)


def clean_new_value(text: str) -> str:
    """Clean extracted new value by stripping modal particles, whitespace, and trailing punctuation."""
    t = text.strip()
    t = _POLITE_PARTICLES_PATTERN.sub("", t).strip()
    t = re.sub(r"[.?!,;:]+$", "", t).strip()
    return t


def extract_modify_components(message: str) -> dict[str, str]:
    """
    Extract components from a decision modification message:
    - raw_target: text specifying what is being changed (e.g. 'quyết định hạ tầng đám mây', 'GCP', 'database')
    - topic: normalized domain/scope topic (e.g. 'hạ tầng đám mây', 'database')
    - new_value: clean proposed replacement value (e.g. 'AWS', 'MongoDB')
    """
    msg = message.strip()

    # Pattern 1: X (thay|đổi|chuyển|cập nhật) [Target] (sang|thành|bằng|to|with) [NewValue]
    m = re.search(
        r"(?i)(?:đổi|thay\s+đổi|thay|chuyển|cập\s+nhật|sửa)\s+(.+?)\s+(?:sang|thành|bằng|to|with)\s+(.+)",
        msg,
    )
    if m:
        raw_target = m.group(1).strip()
        raw_new = m.group(2).strip()
        cleaned_target = re.sub(
            r"(?i)^(?:quyết\s+định|lựa\s+chọn|kế\s+hoạch|mục\s+tiêu|phương\s+án)\s*(?:về|cho|của)?\s*",
            "",
            raw_target,
        ).strip()
        cleaned_target = re.sub(r"^(?:về|cho|của)\s+", "", cleaned_target, flags=re.IGNORECASE).strip()
        new_val = clean_new_value(raw_new)
        return {
            "raw_target": raw_target,
            "topic": cleaned_target or raw_target,
            "new_value": new_val,
        }

    # Pattern 2: Chọn [NewValue] thay vì [Target]
    m2 = re.search(r"(?i)(?:chọn|dùng|sử\s+dụng)\s+(.+?)\s+thay\s+vì\s+(.+)", msg)
    if m2:
        raw_new = m2.group(1).strip()
        raw_target = m2.group(2).strip()
        cleaned_target = _MODIFY_PREFIX_PATTERN.sub("", raw_target).strip()
        return {
            "raw_target": raw_target,
            "topic": cleaned_target or raw_target,
            "new_value": clean_new_value(raw_new),
        }

    # Pattern 3: Đổi sang / chuyển sang [NewValue] (no explicit target mentioned)
    m3 = re.search(r"(?i)(?:đổi|chuyển|thay|cập\s+nhật)\s+(?:sang|thành|bằng|to)\s+(.+)", msg)
    if m3:
        raw_new = m3.group(1).strip()
        return {
            "raw_target": "",
            "topic": "",
            "new_value": clean_new_value(raw_new),
        }

    # Fallback: text after keywords like sang, thành, bằng
    fallback_val = re.sub(
        r"(?i)^.+?(?:thành|sang|bằng|to|with|use|dùng)\s+", "", msg
    ).strip()
    return {
        "raw_target": "",
        "topic": "",
        "new_value": clean_new_value(fallback_val or msg),
    }


def synthesize_full_decision(
    old_content: str,
    message: str,
    topic: Optional[str] = None,
    new_value: Optional[str] = None,
) -> str:
    """
    Synthesize a grammatically complete, scoped new decision sentence.
    Preserves subject, verb, and scope of old decision while substituting the new choice.
    Avoids saving sentence fragments like 'AWS nhé.'.
    """
    old_c = old_content.strip()
    # Strip any trailing punctuation from old content for clean processing
    clean_old = re.sub(r"[.?!]+$", "", old_c).strip()

    if not new_value or topic is None:
        comps = extract_modify_components(message)
        new_val = new_value or comps["new_value"]
        top = topic if topic is not None else comps["topic"]
    else:
        new_val = clean_new_value(new_value)
        top = topic

    if not new_val:
        return old_c

    # Priority 1: If user explicitly named an entity to replace (e.g. "Đổi DigitalOcean sang Linode", "Thay TailwindCSS bằng Bootstrap")
    # and the target expression is not a generic topic phrase like "hạ tầng", "cơ sở dữ liệu", "quyết định".
    topic_indicators = {
        "quyết định", "lựa chọn", "kế hoạch", "mục tiêu",
        "hạ tầng", "đám mây", "cơ sở dữ liệu", "database",
        "giao diện", "frontend", "backend", "ngân sách",
        "địa điểm", "dự án", "hệ thống",
    }
    raw_target = (extract_modify_components(message).get("raw_target") or "").strip()
    is_topic_phrase = any(w in raw_target.lower() for w in topic_indicators)
    if raw_target and not is_topic_phrase:
        escaped_target = re.escape(raw_target)
        if re.search(rf"(?i)\b{escaped_target}\b", clean_old):
            updated = re.sub(rf"(?i)\b{escaped_target}\b", new_val, clean_old, count=1)
            return updated.strip()

    # Priority 2: Verb + Preposition slot pattern
    # [Subject/Prefix] <Verb> <OldEntity> <Preposition> <Scope>
    # e.g. "Chúng tôi chọn GCP cho dự án hạ tầng đám mây năm 2026"
    # e.g. "Công ty sử dụng PostgreSQL làm cơ sở dữ liệu chính từ Q3"
    slot_pattern = re.compile(
        r"(?i)^(?P<prefix>.*?\b(?:chọn|dùng|sử\s+dụng|triển\s+khai|ưu\s+tiên|chốt|lựa\s+chọn)\s+)"
        r"(?P<old_entity>[^,]+?)"
        r"(?P<suffix>\s+(?:cho|làm|tại|ở|vào|từ|với|trong|theo|nhưng|trên|dưới)\b.*)$"
    )
    m_slot = slot_pattern.match(clean_old)
    if m_slot:
        prefix = m_slot.group("prefix")
        suffix = m_slot.group("suffix")
        return f"{prefix}{new_val}{suffix}".strip()

    # Priority 2: Copula / equality pattern: [Topic/Prefix] <là|:> <OldEntity> [<Suffix>]
    # e.g. "Ngân sách marketing tháng tới là 50 triệu."
    copula_pattern = re.compile(
        r"(?i)^(?P<prefix>.*?\b(?:là|:|=)\s+)"
        r"(?P<old_entity>[^,]+?)"
        r"(?P<suffix>(?:\s+(?:cho|làm|tại|ở|vào|từ|với|trong|theo|nhưng|trên|dưới)\b.*)?)$"
    )
    m_copula = copula_pattern.match(clean_old)
    if m_copula:
        prefix = m_copula.group("prefix")
        suffix = m_copula.group("suffix")
        return f"{prefix}{new_val}{suffix}".strip()

    # Priority 3: End-of-sentence verb pattern: [Subject/Prefix] <Verb> <OldEntity>$
    # e.g. "Kế hoạch là Sanic" or "Dự án chọn Linode"
    end_verb_pattern = re.compile(
        r"(?i)^(?P<prefix>.*?\b(?:chọn|dùng|sử\s+dụng|triển\s+khai|ưu\s+tiên|chốt|lựa\s+chọn|là)\s+)"
        r"(?P<old_entity>[^,]+)$"
    )
    m_end = end_verb_pattern.match(clean_old)
    if m_end:
        prefix = m_end.group("prefix")
        return f"{prefix}{new_val}".strip()

    # Priority 4: If user explicitly named an entity to replace (and it's not a general topic word)
    if top:
        top_words = top.strip()
        escaped_top = re.escape(top_words)
        if re.search(rf"(?i)\b{escaped_top}\b", clean_old):
            updated = re.sub(rf"(?i)\b{escaped_top}\b", new_val, clean_old, count=1)
            return updated.strip()

    # Priority 5: Fallback preservation: if old_content had a clear subject/scope, retain it
    if top:
        return f"Quyết định về {top}: {new_val}"

    # If old content is a single word or short entity, return clean new value
    if len(clean_old.split()) <= 2:
        return new_val

    # Default fallback: synthesize clean full sentence
    return f"Quyết định thay đổi: {new_val} (thay thế cho: {clean_old})"


def _tokenize_meaningful_words(text: str) -> set[str]:
    """Tokenize words excluding command verbs, prepositions, and grammatical noise."""
    stop = {
        "đổi", "thay", "chuyển", "sửa", "cập", "nhật", "chọn", "lựa",
        "quyết", "định", "kế", "hoạch", "mục", "tiêu", "ý", "này",
        "sang", "thành", "bằng", "to", "with", "lại", "nữa",
        "nhé", "nha", "nhe", "nhá", "ạ", "đi", "nhỉ", "với", "ngay",
        "cho", "của", "tôi", "chúng", "mình", "bạn", "là", "và", "có", "gì", "nào",
        "hiện", "tại", "vừa", "nói", "trước", "đó", "hôm", "tuần", "tháng", "năm",
    }
    words = re.findall(r"\w+", text.lower(), flags=re.UNICODE)
    return {w for w in words if w not in stop and len(w) > 1}


def find_best_matching_decision(
    memories: list[dict], message: str
) -> tuple[Optional[dict], bool, list[dict]]:
    """
    Identify the target active decision memory to modify.
    Returns: (best_match, is_ambiguous, candidate_list)

    Disambiguation rules:
    - Only considers active decisions / preferences / goals.
    - Extracts meaningful topic/scope words from user message (excluding the proposed new value).
    - If multiple candidates match topic equally or user didn't specify topic when multiple exist,
      returns (None, True, candidates) to prompt for clarification rather than arbitrarily guessing.
    - If exactly one candidate matches best, returns (candidate, False, [candidate]).
    """
    decisions = [m for m in memories if m.get("info_type") in ("decision", "preference", "goal") and m.get("is_active", 1) == 1]
    if not decisions:
        return None, False, []

    comps = extract_modify_components(message)
    new_val_words = _tokenize_meaningful_words(comps.get("new_value", ""))
    target_text = comps.get("raw_target") or comps.get("topic") or message
    msg_meaningful = _tokenize_meaningful_words(target_text) - new_val_words

    # If user message provided no meaningful topic words:
    if not msg_meaningful:
        if len(decisions) == 1:
            return decisions[0], False, [decisions[0]]
        # Multiple decisions exist and user gave no distinguishing topic
        return None, True, decisions

    # Score each decision against meaningful query tokens
    scored = []
    for mem in decisions:
        mem_words = _tokenize_meaningful_words(mem.get("content", ""))
        overlap = len(msg_meaningful & mem_words)
        scored.append((overlap, mem))

    scored.sort(key=lambda x: x[0], reverse=True)
    best_score = scored[0][0]

    # If no decision matched any topic words:
    if best_score == 0:
        if len(decisions) == 1:
            return decisions[0], False, [decisions[0]]
        return None, True, decisions

    # Check for ambiguity: multiple decisions sharing top score
    top_candidates = [m for score, m in scored if score == best_score]
    if len(top_candidates) > 1:
        unique_contents = {m["content"].strip().lower() for m in top_candidates}
        if len(unique_contents) > 1:
            return None, True, top_candidates

    return scored[0][1], False, [scored[0][1]]
