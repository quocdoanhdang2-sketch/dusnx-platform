import pytest
from apps.ai_api.decision_updater import (
    clean_new_value,
    extract_modify_components,
    synthesize_full_decision,
    find_best_matching_decision,
)


def test_clean_new_value():
    assert clean_new_value("AWS nhé.") == "AWS"
    assert clean_new_value("AWS nha!") == "AWS"
    assert clean_new_value("MongoDB đi ạ.") == "MongoDB"
    assert clean_new_value("70 triệu nhé") == "70 triệu"
    assert clean_new_value("màu tối") == "màu tối"


def test_extract_modify_components():
    c1 = extract_modify_components("Đổi quyết định hạ tầng đám mây sang AWS nhé.")
    assert c1["new_value"] == "AWS"
    assert "hạ tầng đám mây" in c1["topic"]

    c2 = extract_modify_components("Thay cơ sở dữ liệu chính thành PostgreSQL đi")
    assert c2["new_value"] == "PostgreSQL"
    assert "cơ sở dữ liệu chính" in c2["topic"]

    c3 = extract_modify_components("Thay TailwindCSS bằng Bootstrap")
    assert c3["new_value"] == "Bootstrap"
    assert c3["raw_target"] == "TailwindCSS"


def test_synthesize_full_decision():
    # Case 1: Cloud decision (GCP -> AWS)
    old1 = "Chúng tôi chọn GCP cho dự án hạ tầng đám mây năm 2026"
    req1 = "Đổi quyết định hạ tầng đám mây sang AWS nhé."
    syn1 = synthesize_full_decision(old1, req1)
    assert syn1 == "Chúng tôi chọn AWS cho dự án hạ tầng đám mây năm 2026"
    assert "nhé" not in syn1
    assert not syn1.endswith("..")

    # Case 2: Database decision (PostgreSQL -> MongoDB)
    old2 = "Công ty sử dụng PostgreSQL làm cơ sở dữ liệu chính từ Q3."
    req2 = "Đổi cơ sở dữ liệu chính sang MongoDB nhé."
    syn2 = synthesize_full_decision(old2, req2)
    assert syn2 == "Công ty sử dụng MongoDB làm cơ sở dữ liệu chính từ Q3"

    # Case 3: Explicit old entity replacement (TailwindCSS -> Bootstrap)
    old3 = "Nhóm ưu tiên TailwindCSS cho giao diện web"
    req3 = "Thay TailwindCSS bằng Bootstrap"
    syn3 = synthesize_full_decision(old3, req3)
    assert syn3 == "Nhóm ưu tiên Bootstrap cho giao diện web"

    # Case 4: Copula structure (Marketing budget)
    old4 = "Ngân sách marketing tháng tới là 50 triệu."
    req4 = "Đổi ngân sách marketing thành 70 triệu đi."
    syn4 = synthesize_full_decision(old4, req4)
    assert syn4 == "Ngân sách marketing tháng tới là 70 triệu"

    # Case 5: End-of-sentence verb
    old5 = "Kế hoạch là Sanic"
    req5 = "Đổi sang Tornado nha"
    syn5 = synthesize_full_decision(old5, req5)
    assert syn5 == "Kế hoạch là Tornado"


def test_find_best_matching_decision_disambiguation():
    memories = [
        {"memory_id": "m1", "info_type": "decision", "content": "Chọn GCP cho hạ tầng đám mây", "is_active": 1},
        {"memory_id": "m2", "info_type": "decision", "content": "Chọn React cho giao diện web", "is_active": 1},
    ]

    # Specific topic matches m1
    match1, is_ambig1, cands1 = find_best_matching_decision(memories, "Đổi quyết định hạ tầng sang AWS nhé.")
    assert not is_ambig1
    assert match1 is not None and match1["memory_id"] == "m1"

    # Specific topic matches m2
    match2, is_ambig2, cands2 = find_best_matching_decision(memories, "Đổi giao diện sang Vue nhé.")
    assert not is_ambig2
    assert match2 is not None and match2["memory_id"] == "m2"

    # Ambiguous modify request without topic -> asks clarification
    match3, is_ambig3, cands3 = find_best_matching_decision(memories, "Đổi quyết định sang AWS nhé.")
    assert is_ambig3
    assert match3 is None
    assert len(cands3) == 2
