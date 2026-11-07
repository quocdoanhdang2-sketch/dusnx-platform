"""Authoritative runtime clock for date/time answers.

The model has a fixed training cutoff and must never be asked to guess today's
date. This module is the single source of truth used both for a deterministic
fast path and for the provider system prompt.
"""
from __future__ import annotations

import os
import re
from datetime import datetime, timedelta
from typing import Optional

_DEFAULT_TIMEZONE = ""
_WEEKDAY_VI = ["Thứ Hai", "Thứ Ba", "Thứ Tư", "Thứ Năm", "Thứ Sáu", "Thứ Bảy", "Chủ Nhật"]
_WEEKDAY_EN = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]


def _timezone_name() -> str:
    return (os.getenv("DUSNX_TIMEZONE", _DEFAULT_TIMEZONE) or "").strip()


def now_local() -> datetime:
    """Host-local time by default; DUSNX_TIMEZONE pins an IANA zone when needed."""
    name = _timezone_name()
    if name:
        try:
            from zoneinfo import ZoneInfo

            return datetime.now(ZoneInfo(name))
        except Exception:
            pass
    return datetime.now().astimezone()


def _utc_offset_label(moment: datetime) -> str:
    offset = moment.utcoffset() or timedelta(0)
    total_minutes = int(offset.total_seconds() // 60)
    sign = "+" if total_minutes >= 0 else "-"
    total_minutes = abs(total_minutes)
    return f"UTC{sign}{total_minutes // 60:02d}:{total_minutes % 60:02d}"


def clock_context(language: str = "vi") -> str:
    """One authoritative sentence injected into the provider system prompt."""
    moment = now_local()
    offset = _utc_offset_label(moment)
    if language == "en":
        return (f"Current date and time: {_WEEKDAY_EN[moment.weekday()]}, "
                f"{moment:%d/%m/%Y} at {moment:%H:%M} ({offset}).")
    return (f"Thời điểm hiện tại: {_WEEKDAY_VI[moment.weekday()]}, "
            f"ngày {moment:%d/%m/%Y} lúc {moment:%H:%M} ({offset}).")


def _normalize(text: str) -> str:
    value = (text or "").strip().lower()
    value = re.sub(r"[\u00a0\s]+", " ", value)
    value = re.sub(r"[?!.。！？]+$", "", value).strip()
    value = re.sub(r"^(?:cho (?:tôi|mình|tao|em) hỏi|cho hỏi|xin hỏi)[,:\s]+", "", value)
    value = re.sub(r"\s+(?:ạ|nhỉ|thế|vậy|vậy ạ|thế ạ)$", "", value).strip()
    value = re.sub(r"[,]+", " ", value).strip()
    return value


_CLOCK_PATTERNS = {
    "today_tomorrow": [
        r"hôm nay(?: là)?(?: ngày)? (?:bao nhiêu|mấy)(?: ngày)? (?:và|,)? (?:ngày )?mai(?: là)? thứ mấy",
        r"hôm nay(?: là)? thứ mấy (?:và|,)? (?:ngày )?mai(?: là)? thứ mấy",
        r"what(?:'s| is) today'?s date and what day is (?:it )?tomorrow",
        r"what day is (?:it )?today and (?:what day is )?tomorrow",
    ],
    "tomorrow": [
        r"(?:ngày )?mai(?: là)? thứ mấy",
        r"ngày mai(?: là)? (?:ngày )?(?:bao nhiêu|mấy)",
        r"what day is (?:it )?tomorrow",
        r"what(?:'s| is) tomorrow'?s date",
    ],
    "date": [
        r"hôm nay(?: là)?(?: ngày)? (?:bao nhiêu|mấy|số mấy)(?: ngày)?",
        r"hôm nay(?: là)? ngày (?:bao nhiêu|mấy|số mấy)",
        r"(?:hôm )?nay(?: là)? ngày (?:bao nhiêu|mấy|số mấy)",
        r"ngày hôm nay(?: là)?(?: ngày)? (?:bao nhiêu|mấy)",
        r"hôm nay(?: là)? ngày (?:thứ )?mấy",
        r"hôm nay(?: là)? thứ mấy",
        r"(?:bây giờ|hiện tại|giờ này) là ngày (?:bao nhiêu|mấy)",
        r"what(?:'s| is) (?:the )?date(?: today)?",
        r"what is today'?s date",
        r"today'?s date",
        r"what day is (?:it )?today",
        r"what(?:'s| is) today'?s date",
        r"what is the current date",
    ],
    "time": [
        r"(?:bây giờ|hiện tại|giờ này) (?:là )?mấy giờ",
        r"mấy giờ rồi",
        r"giờ (?:hiện tại|này|bây giờ) (?:là )?mấy giờ",
        r"what time is it",
        r"what(?:'s| is) the (?:current )?time",
        r"current time",
    ],
}

_COMPILED = {kind: [re.compile(rf"^(?:{pat})$") for pat in patterns]
             for kind, patterns in _CLOCK_PATTERNS.items()}

_TIME_HINT = re.compile(r"\b(?:giờ|time)\b")

_CLAIM_PATTERNS = [
    re.compile(r"(?:hôm nay|nay)\s*(?:là\s*)?(?:ngày\s*)?(\d{1,2})[/-](\d{1,2})[/-](\d{2,4})", re.I),
    re.compile(r"(?:hôm nay|nay)\s*(?:là\s*)?(?:ngày\s*)?(\d{1,2})\s*tháng\s*(\d{1,2})\s*(?:năm\s*)?(\d{4})", re.I),
    re.compile(r"(?:hôm nay|nay)\s*(?:là\s*)?(?:ngày\s*)?(\d{4})-(\d{2})-(\d{2})", re.I),
    re.compile(r"today(?:'s date)?\s+is\s+(?:the\s+)?(\d{1,2})[/-](\d{1,2})[/-](\d{2,4})", re.I),
    re.compile(r"today(?:'s date)?\s+is\s+(\d{4})-(\d{2})-(\d{2})", re.I),
]


def detect_stated_today_date(text: str):
    """Extract an explicit "today is <date>" claim, if the message makes one."""
    value = (text or "").strip()
    for pattern in _CLAIM_PATTERNS:
        match = pattern.search(value)
        if not match:
            continue
        groups = match.groups()
        try:
            if len(groups[0]) == 4:
                year, month, day = int(groups[0]), int(groups[1]), int(groups[2])
            else:
                day, month, year = int(groups[0]), int(groups[1]), int(groups[2])
                year = year + 2000 if year < 100 else year
            return datetime(year, month, day).date()
        except ValueError:
            continue
    return None


def stated_date_correction(text: str, language: str = "vi") -> Optional[str]:
    """Deterministic correction when a stated "today" differs from the clock."""
    claim = detect_stated_today_date(text)
    if claim is None:
        return None
    moment = now_local()
    if claim == moment.date():
        return None
    if language == "en":
        return (f"That is not correct. Today is {_WEEKDAY_EN[moment.weekday()]}, "
                f"{moment:%d/%m/%Y} according to the system clock, not {claim:%d/%m/%Y}.")
    return (f"Không đúng. Hôm nay là {_WEEKDAY_VI[moment.weekday()]}, ngày {moment:%d/%m/%Y} "
            f"theo đồng hồ hệ thống, không phải {claim:%d/%m/%Y}.")


def detect_clock_query(text: str) -> Optional[str]:
    """Return 'date', 'time', or None for a message that only asks the clock.

    Deliberately strict: a request that also contains another task must go to
    the provider, which receives the same authoritative clock in its prompt.
    """
    normalized = _normalize(text)
    if not normalized or len(normalized) > 80:
        return None
    for kind in ("today_tomorrow", "tomorrow"):
        if any(p.match(normalized) for p in _COMPILED[kind]):
            return kind
    if _TIME_HINT.search(normalized) and any(p.match(normalized) for p in _COMPILED["time"]):
        return "time"
    if any(p.match(normalized) for p in _COMPILED["date"]):
        return "date"
    return None


def answer_clock_query(kind: str, language: str = "vi") -> str:
    moment = now_local()
    date_text = (f"{_WEEKDAY_VI[moment.weekday()]}, ngày {moment:%d/%m/%Y}"
                 if language != "en" else
                 f"{_WEEKDAY_EN[moment.weekday()]}, {moment:%d/%m/%Y}")
    tomorrow = moment + timedelta(days=1)
    tomorrow_text = (f"{_WEEKDAY_VI[tomorrow.weekday()]}, ngày {tomorrow:%d/%m/%Y}"
                     if language != "en" else
                     f"{_WEEKDAY_EN[tomorrow.weekday()]}, {tomorrow:%d/%m/%Y}")
    if kind == "today_tomorrow":
        if language == "en":
            return f"Today is {date_text}. Tomorrow is {tomorrow_text}."
        return f"Hôm nay là {date_text}. Ngày mai là {tomorrow_text}."
    if kind == "tomorrow":
        if language == "en":
            return f"Tomorrow is {tomorrow_text}."
        return f"Ngày mai là {tomorrow_text}."
    if kind == "time":
        if language == "en":
            return f"It is {moment:%H:%M} on {date_text} ({_utc_offset_label(moment)})."
        return f"Bây giờ là {moment:%H:%M}, {date_text} ({_utc_offset_label(moment)})."
    if language == "en":
        return f"Today is {date_text}."
    return f"Hôm nay là {date_text}."
