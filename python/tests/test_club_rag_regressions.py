"""Regressions for club retrieval ordering and extractive answers.

These pin the behaviours fixed after the P0 review: a dated milestone row must
beat the surrounding prose, a date in a section heading must be quotable, a
compound overview question must fill every slot from the "Thông tin chung"
section, and "đăng ký thế nào" must quote the procedure rather than the
usage-duration limit that shares the same section.
"""
from pathlib import Path

import pytest

from apps.ai_api import rag

CLUB_INDEX = Path(__file__).resolve().parents[2] / "runtime" / "club-rag" / "rag.db"


@pytest.fixture(autouse=True)
def club_index(monkeypatch):
    if not CLUB_INDEX.is_file():
        pytest.skip("Club RAG index not built in this workspace")
    # Pin the club index: rag.database_path() may otherwise resolve to the
    # repository index or the checked-in python/data copy.
    monkeypatch.setenv("DUSNX_RAG_DB", str(CLUB_INDEX))


def _answer(question: str) -> str:
    hits = rag.retrieve(question, top_k=5)
    assert hits, question
    return rag.answer_from_hits(question, hits, language="vi") or ""


def test_date_range_milestone_row_is_quoted():
    answer = _answer("Tuyển thành viên đợt 2 nhận đơn từ ngày nào đến ngày nào?")
    assert "01/12/2026" in answer and "15/12/2026" in answer
    assert "nhận đơn" in answer.lower()


def test_workshop_date_lives_in_section_heading():
    answer = _answer("Workshop Git & GitHub tổ chức khi nào?")
    assert "27/11/2026" in answer


def test_team_building_overview_fills_destination_date_and_fee():
    answer = _answer("Team building đi đâu, ngày nào, phí bao nhiêu?")
    for needle in ("Thung Lũng Xanh", "27/12/2026", "100.000"):
        assert needle in answer


def test_lab_registration_quotes_procedure_not_duration_limit():
    answer = _answer("Muốn dùng phòng lab phải đăng ký thế nào?")
    assert "đăng ký trước ít nhất 1 ngày" in answer
    assert "3 tiếng" not in answer


def test_domain_classifier_accepts_club_questions_and_rejects_general():
    for question in (
        "CLB IT sinh hoạt vào thứ mấy, mấy giờ?",
        "Quỹ CLB đóng bao nhiêu một tháng?",
        "Lịch workshop tháng 12?",
        "Muốn dùng phòng lab phải đăng ký thế nào?",
    ):
        assert rag.is_domain_question(question), question
    for question in (
        "Giá vàng hôm nay bao nhiêu một chỉ?",
        "Cách nấu phở bò ngon tại nhà?",
        "Thời tiết Hà Nội ngày mai thế nào?",
        "Đội nào vô địch World Cup 2026?",
    ):
        assert not rag.is_domain_question(question), question
