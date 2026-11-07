from datetime import datetime, timedelta, timezone

from apps.ai_api import runtime_clock


def test_clock_query_detection_vi_and_en():
    assert runtime_clock.detect_clock_query("Hôm nay là ngày bao nhiêu?") == "date"
    assert runtime_clock.detect_clock_query("hôm nay ngày mấy") == "date"
    assert runtime_clock.detect_clock_query("Hôm nay thứ mấy?") == "date"
    assert runtime_clock.detect_clock_query("Bây giờ là mấy giờ?") == "time"
    assert runtime_clock.detect_clock_query("What is today's date?") == "date"
    assert runtime_clock.detect_clock_query("What time is it?") == "time"
    assert runtime_clock.detect_clock_query("Hôm nay ngày bao nhiêu và ngày mai là thứ mấy?") == "today_tomorrow"
    assert runtime_clock.detect_clock_query("Ngày mai là thứ mấy?") == "tomorrow"


def test_clock_detection_leaves_mixed_tasks_to_provider():
    assert runtime_clock.detect_clock_query(
        "Hôm nay là ngày 7 tháng 11 năm 2026. Ghi nhớ giúp tôi."
    ) is None
    assert runtime_clock.detect_clock_query("Giải thích kiến trúc DUSN-X hôm nay") is None
    assert runtime_clock.detect_clock_query("Tóm tắt giúp tôi tài liệu này") is None


def test_clock_answers_use_fixed_runtime_clock(monkeypatch):
    fixed = datetime(2026, 11, 7, 7, 25, tzinfo=timezone(timedelta(hours=-6)))
    monkeypatch.setattr(runtime_clock, "now_local", lambda: fixed)

    assert runtime_clock.answer_clock_query("date", "vi") == "Hôm nay là Thứ Bảy, ngày 07/11/2026."
    assert runtime_clock.answer_clock_query("date", "en") == "Today is Saturday, 07/11/2026."
    assert runtime_clock.answer_clock_query("time", "vi") == (
        "Bây giờ là 07:25, Thứ Bảy, ngày 07/11/2026 (UTC-06:00)."
    )
    assert runtime_clock.answer_clock_query("tomorrow", "vi") == "Ngày mai là Chủ Nhật, ngày 08/11/2026."
    assert runtime_clock.answer_clock_query("today_tomorrow", "en") == (
        "Today is Saturday, 07/11/2026. Tomorrow is Sunday, 08/11/2026."
    )


def test_clock_context_matches_runtime_clock(monkeypatch):
    fixed = datetime(2026, 11, 7, 7, 25, tzinfo=timezone(timedelta(hours=-6)))
    monkeypatch.setattr(runtime_clock, "now_local", lambda: fixed)

    assert runtime_clock.clock_context("vi") == (
        "Thời điểm hiện tại: Thứ Bảy, ngày 07/11/2026 lúc 07:25 (UTC-06:00)."
    )
    assert runtime_clock.clock_context("en") == (
        "Current date and time: Saturday, 07/11/2026 at 07:25 (UTC-06:00)."
    )


def test_stated_today_date_is_parsed():
    assert runtime_clock.detect_stated_today_date("Hôm nay là ngày 1 tháng 1 năm 2025.") == (
        runtime_clock.datetime(2025, 1, 1).date()
    )
    assert runtime_clock.detect_stated_today_date("hôm nay là 1/1/2025") == (
        runtime_clock.datetime(2025, 1, 1).date()
    )
    assert runtime_clock.detect_stated_today_date("Today is 2025-01-01") == (
        runtime_clock.datetime(2025, 1, 1).date()
    )
    assert runtime_clock.detect_stated_today_date("Hôm nay trời đẹp") is None


def test_stated_wrong_date_is_corrected_but_matching_date_is_not(monkeypatch):
    fixed = datetime(2026, 11, 7, 7, 25, tzinfo=timezone(timedelta(hours=-6)))
    monkeypatch.setattr(runtime_clock, "now_local", lambda: fixed)

    assert runtime_clock.stated_date_correction("Hôm nay là ngày 1 tháng 1 năm 2025.", "vi") == (
        "Không đúng. Hôm nay là Thứ Bảy, ngày 07/11/2026 theo đồng hồ hệ thống, không phải 01/01/2025."
    )
    assert runtime_clock.stated_date_correction("Sai rồi, hôm nay là ngày 1 tháng 1 năm 2025.", "vi") is not None
    assert runtime_clock.stated_date_correction("Hôm nay là ngày 7 tháng 11 năm 2026.", "vi") is None
    assert runtime_clock.stated_date_correction("Hôm nay trời đẹp.", "vi") is None
    assert runtime_clock.stated_date_correction("Today is 2025-01-01", "en") == (
        "That is not correct. Today is Saturday, 07/11/2026 according to the system clock, not 01/01/2025."
    )
