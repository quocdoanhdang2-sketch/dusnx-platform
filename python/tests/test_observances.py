"""Observe-date questions must be answered from the checked calendar, not guessed."""
from test_week2_acceptance import _register_and_login
from test_week2_acceptance import client as client  # noqa: PLC0414 -- pytest fixture re-export
from test_week2_acceptance import isolated_week2_env as isolated_week2_env  # noqa: PLC0414

from apps.ai_api.observances import answer_observance_question


def test_known_dates_are_answered_deterministically():
    reply = answer_observance_question("Chào ngày mới vui vẻ nhé bạn ui, 20/11 là ngày gì")
    assert "Nhà giáo Việt Nam" in reply
    assert "Nhà giáo Việt Nam" in answer_observance_question("20/11/2026 là ngày gì?")
    assert "Quốc khánh" in answer_observance_question("ngày 2 tháng 9 là ngày gì?")
    assert "Teachers' Day" in answer_observance_question("What is 20/11?", "en")


def test_follow_up_and_bare_date_are_answered():
    assert "Phụ nữ Việt Nam" in answer_observance_question("thế còn ngày 20/10")
    assert "Phụ nữ Việt Nam" in answer_observance_question("20/10?")
    assert "Quốc khánh" in answer_observance_question("Còn 2/9 thì sao?")


def test_year_specific_event_is_not_invented():
    reply = answer_observance_question("2/9/1973 là ngày gì?")
    assert "Quốc khánh" in reply
    assert "không có thông tin" in reply.lower()
    assert "1973" in reply


def test_scheduling_and_other_tasks_do_not_trigger():
    assert answer_observance_question("Đặt lịch họp vào 20/11 lúc 9h") is None
    assert answer_observance_question("Nhắc tôi 20/11 mua quà") is None
    assert answer_observance_question("20/11 là thứ mấy?") is None


def test_unknown_date_is_reported_not_guessed():
    reply = answer_observance_question("15/7 là ngày gì?")
    assert "không có thông tin" in reply.lower()
    assert "15/07" in reply


def test_invalid_or_multiple_dates_fall_through():
    assert answer_observance_question("31/2 là ngày gì?") is None
    assert answer_observance_question("20/11 và 2/9 là ngày gì?") is None


def test_chat_answers_observance_without_calling_the_provider(client):
    _, token = _register_and_login(client, "observance_owner")
    headers = {"Authorization": f"Bearer {token}"}
    sid = client.post("/v1/sessions", headers=headers, json={}).json()["session_id"]
    res = client.post("/v1/chat", headers=headers, json={
        "session_id": sid,
        "message": "20/11 là ngày gì?",
        "preferred_language": "auto",
    }).json()
    assert res["provider_called"] is False
    assert res["provider_ok"] is True
    assert res["response_source"] == "observance_calendar"
    assert "Nhà giáo Việt Nam" in res["reply"]
