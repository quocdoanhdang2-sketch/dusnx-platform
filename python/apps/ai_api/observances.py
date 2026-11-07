"""Deterministic answers for common Vietnamese observance dates.

The small local model does not reliably know Vietnamese holidays and will
invent an answer when asked. Date-identity questions are therefore answered
from a short verified calendar instead of the model. Dates outside the
calendar get an explicit "not verified" answer rather than a guess.
"""
from __future__ import annotations

import re
from datetime import date
from typing import Optional

# (day, month) -> {"vi": (name, note), "en": (name, note)}
CALENDAR = {
    (1, 1): {
        "vi": ("Tết Dương lịch", "ngày đầu tiên của năm mới theo lịch Gregory"),
        "en": ("New Year's Day", "the first day of the year in the Gregorian calendar"),
    },
    (3, 2): {
        "vi": ("Ngày thành lập Đảng Cộng sản Việt Nam", "kỷ niệm ngày thành lập Đảng năm 1930"),
        "en": ("Founding Day of the Communist Party of Vietnam", "commemorates the party's founding in 1930"),
    },
    (8, 3): {
        "vi": ("Ngày Quốc tế Phụ nữ", "tôn vinh phụ nữ và quyền bình đẳng"),
        "en": ("International Women's Day", "honours women and the push for equality"),
    },
    (30, 4): {
        "vi": ("Ngày Giải phóng miền Nam, thống nhất đất nước", "kỷ niệm ngày 30/4/1975"),
        "en": ("Reunification Day", "marks the reunification of Vietnam in 1975"),
    },
    (1, 5): {
        "vi": ("Ngày Quốc tế Lao động", "ngày lễ của người lao động"),
        "en": ("International Workers' Day", "a day honouring workers"),
    },
    (19, 5): {
        "vi": ("Ngày sinh Chủ tịch Hồ Chí Minh", "kỷ niệm ngày sinh năm 1890"),
        "en": ("Birthday of President Ho Chi Minh", "commemorates his birth in 1890"),
    },
    (1, 6): {
        "vi": ("Ngày Quốc tế Thiếu nhi", "ngày dành cho trẻ em"),
        "en": ("International Children's Day", "a day for children"),
    },
    (27, 7): {
        "vi": ("Ngày Thương binh - Liệt sĩ", "tri ân người có công với cách mạng"),
        "en": ("War Invalids and Martyrs' Day", "honours war invalids and martyrs"),
    },
    (2, 9): {
        "vi": ("Quốc khánh Việt Nam", "kỷ niệm Tuyên ngôn Độc lập năm 1945"),
        "en": ("National Day of Vietnam", "commemorates the 1945 Declaration of Independence"),
    },
    (20, 10): {
        "vi": ("Ngày Phụ nữ Việt Nam", "kỷ niệm ngày thành lập Hội Liên hiệp Phụ nữ Việt Nam năm 1930"),
        "en": ("Vietnamese Women's Day", "marks the founding of the Vietnam Women's Union in 1930"),
    },
    (20, 11): {
        "vi": ("Ngày Nhà giáo Việt Nam", "tri ân và tôn vinh những người làm nghề dạy học"),
        "en": ("Vietnamese Teachers' Day", "honours teachers and their work"),
    },
    (22, 12): {
        "vi": ("Ngày thành lập Quân đội nhân dân Việt Nam", "kỷ niệm ngày thành lập năm 1944"),
        "en": ("Founding Day of the Vietnam People's Army", "commemorates its founding in 1944"),
    },
    (24, 12): {
        "vi": ("Giáng sinh", "lễ Kitô giáo mừng Chúa Giêsu sinh ra"),
        "en": ("Christmas", "the Christian celebration of the birth of Jesus"),
    },
}

_DATE = re.compile(
    r"(?<!\d)(\d{1,2})\s*(?:[/\-.]|\s*tháng\s*)\s*(\d{1,2})(?!\d)",
    re.IGNORECASE,
)

_QUESTION = re.compile(
    r"(?i)(?:"
    r"là\s+(?:ngày\s+)?(?:gì|gì\s*\?|ngày\s+lễ\s+gì|kỷ\s+niệm\s+gì|dịp\s+gì)|"
    r"có\s+phải\s+(?:là\s+)?ngày\s+(?:lễ\s+)?gì|"
    r"ngày\s+(?:lễ\s+)?gì|"
    r"^\s*(?:thế\s+)?còn\s+(?:ngày\s+)?\d{1,2}\s*(?:[/\-.]|\s*tháng\s*)\s*\d{1,2}[^?\n]*\??\s*$|"
    r"^\s*\d{1,2}\s*(?:[/\-.]|\s*tháng\s*)\s*\d{1,2}(?:[/\-.]\d{2,4})?\s*\??\s*$|"
    r"what\s+(?:day|holiday)\s+is|"
    r"what\s+is\s+.{0,30}\?*\s*$|"
    r"is\s+.{0,30}a\s+(?:public\s+)?holiday"
    r")"
)

# A date inside a scheduling or errand request is not a date-identity question.
_NOT_IDENTITY = re.compile(
    r"(?i)\b(?:nhắc|nhac|đặt\s*lịch|dat\s*lich|họp|hop|nộp|nop|gửi|gui|đi\s|di\s|"
    r"tổ\s*chức|to\s*chuc|deadline|hạn\s*chót|han\s*chot|remind|schedule|meeting)\b"
)

_YEAR = re.compile(r"(?<!\d)(\d{4})(?!\d)")


def _valid_calendar_date(day: int, month: int) -> bool:
    try:
        date(2000, month, day)
    except ValueError:
        return False
    return True


def answer_observance_question(message: str, language: str = "vi") -> Optional[str]:
    """Answer a single-date identity question, or None when it is a different task."""
    text = (message or "").strip()
    if not text or len(text) > 240:
        return None
    if _NOT_IDENTITY.search(text):
        return None
    if not _QUESTION.search(text):
        return None
    matches = list(_DATE.finditer(text))
    if len(matches) != 1:
        return None
    day, month = int(matches[0].group(1)), int(matches[0].group(2))
    if not _valid_calendar_date(day, month):
        return None
    label = f"{day:02d}/{month:02d}"
    entry = CALENDAR.get((day, month))
    if entry is None:
        if language == "en":
            return (f"I don't have a verified observance entry for {label}. "
                    "I only answer date-identity questions from a small checked calendar, "
                    "so I won't guess.")
        return (f"Mình không có thông tin đã xác minh cho ngày {label}. "
                "Mình chỉ trả lời các ngày lễ phổ biến trong lịch đã kiểm tra, nên sẽ không đoán bừa.")
    name, note = entry.get(language, entry["vi"])
    # A question tied to another year asks about a specific event, not the
    # recurring observance. Answer only the recurring entry and say plainly
    # that the year-specific claim is not verified, so the model cannot invent
    # a historical narrative.
    year_match = _YEAR.search(text)
    other_year = int(year_match.group(1)) if year_match else None
    if other_year is not None and other_year != date.today().year:
        if language == "en":
            return (f"{label} is {name} ({note}). "
                    f"I have no verified information about a separate {other_year} event, "
                    "so I won't guess the details.")
        return (f"{label} là {name} — {note}. "
                f"Mình không có thông tin đã xác minh cho sự kiện riêng của năm {other_year}, "
                "nên sẽ không đoán chi tiết.")
    if language == "en":
        return f"{label} is {name} ({note})."
    return f"{label} là {name} — {note}."
