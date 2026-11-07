"""
Regression tests for Issue B & Issue C:
- Issue B: Task preservation (URL/KEY=VALUE must not hijack user intent into config guide;
  clean URLs without trailing punctuation; URL fetch boundary acknowledgment; no sample variable leakage).
- Issue C: No system instruction regurgitation, prompt leakage detection, clean responses.
NOTE: Tests in this file inspect payload structures and helper logic via mock/unit test.
They are explicit unit tests, NOT real LLM generation runs.
"""
import re
from unittest.mock import patch
import pytest

from apps.ai_api.provider import (
    clean_url,
    sanitize_generated_reply,
    generate_response,
)
from scripts.verify_bilingual_generation import quality_flags


def test_clean_url_strips_trailing_punctuation():
    """URLs must not retain trailing commas, periods, quotes, or brackets."""
    assert clean_url("https://example.org/article,") == "https://example.org/article"
    assert clean_url("https://example.org/article.") == "https://example.org/article"
    assert clean_url("https://example.org/article;") == "https://example.org/article"
    assert clean_url("https://example.org/article)") == "https://example.org/article"
    assert clean_url("https://example.org/article?foo=bar") == "https://example.org/article?foo=bar"
    assert clean_url("https://example.org/path/file.html.") == "https://example.org/path/file.html"


def test_summarize_task_with_url_does_not_hijack_into_config_guide():
    """
    Unit test: Summarization task with a URL must not be prefixed with
    'Hướng dẫn cấu hình...' or altered to a configuration guide.
    Instead, it must acknowledge the offline URL fetch boundary.
    """
    prompt = "Tóm tắt nội dung bài viết tại https://example.org/article, không hướng dẫn cài đặt."

    captured_payloads = []

    def mock_ollama_gen(sys_prompt, user_msg):
        captured_payloads.append({"system": sys_prompt, "user": user_msg})
        return "Unit test mock reply", True, "qwen2.5:0.5b", 10

    with patch("apps.ai_api.provider.get_current_provider", return_value="ollama"), \
         patch("apps.ai_api.provider._ollama_generate", side_effect=mock_ollama_gen):
        res = generate_response(prompt, memories=[], intent="chat", response_language="vi")
        assert res[1] is True

    assert len(captured_payloads) == 1
    sent_user_msg = captured_payloads[0]["user"]
    sent_sys_prompt = captured_payloads[0]["system"]

    # Must NOT turn into configuration instructions
    assert "Hướng dẫn cấu hình" not in sent_user_msg
    assert "DUSNX_PORT=8088" not in sent_user_msg
    assert "DUSNX_PORT=8088" not in sent_sys_prompt

    # Must contain offline boundary guidance for external URL fetch
    assert "Chỉ dẫn:" in sent_user_msg or "DUSN-X hiện chưa có tính năng" in sent_user_msg
    assert "https://example.org/article" in sent_user_msg


def test_translation_task_with_key_value_remains_translation():
    """
    Unit test: Translation task containing KEY=VALUE remains a translation task,
    does NOT become a configuration guide, and preserves entity verbatim.
    """
    prompt = "Dịch đoạn văn sau sang tiếng Việt: Set APP_ENV=production before deploying."

    captured_payloads = []

    def mock_ollama_gen(sys_prompt, user_msg):
        captured_payloads.append({"system": sys_prompt, "user": user_msg})
        return "Set APP_ENV=production trước khi triển khai.", True, "qwen2.5:0.5b", 12

    with patch("apps.ai_api.provider.get_current_provider", return_value="ollama"), \
         patch("apps.ai_api.provider._ollama_generate", side_effect=mock_ollama_gen):
        res = generate_response(prompt, memories=[], intent="chat", response_language="vi")
        assert res[1] is True

    assert len(captured_payloads) == 1
    sent_user_msg = captured_payloads[0]["user"]

    assert "Hướng dẫn cấu hình" not in sent_user_msg
    assert "DUSNX_PORT=8088" not in sent_user_msg
    assert "APP_ENV=production" in sent_user_msg


def test_clean_query_without_entities_never_injects_sample_variables():
    """Queries without entities or URLs must never have sample constants injected."""
    prompt = "Làm thế nào để duy trì sự tập trung hiệu quả khi làm việc từ xa?"

    captured_payloads = []

    def mock_ollama_gen(sys_prompt, user_msg):
        captured_payloads.append({"system": sys_prompt, "user": user_msg})
        return "Lời khuyên tập trung...", True, "qwen2.5:0.5b", 15

    with patch("apps.ai_api.provider.get_current_provider", return_value="ollama"), \
         patch("apps.ai_api.provider._ollama_generate", side_effect=mock_ollama_gen):
        generate_response(prompt, memories=[], intent="chat", response_language="vi")

    sent_user_msg = captured_payloads[0]["user"]
    sent_sys_prompt = captured_payloads[0]["system"]

    assert "DUSNX_PORT=8088" not in sent_user_msg
    assert "DUSNX_PORT=8088" not in sent_sys_prompt
    assert "https://api.dusnx.org/v1/auth" not in sent_user_msg
    assert "https://api.dusnx.org/v1/auth" not in sent_sys_prompt


def test_sanitize_generated_reply_removes_instruction_leakage():
    """Sanitizer must strip accidental system prompt headers echoed by small models."""
    leaked_output_1 = (
        "Quan trọng:\n"
        "- Trả lời trực tiếp câu hỏi của người dùng dựa trên thông tin trí nhớ đang hiệu lực ở trên.\n"
        "DUSN-X có các tính năng cốt lõi: quản lý trí nhớ dài hạn và router đa tác tử."
    )
    cleaned_1 = sanitize_generated_reply(leaked_output_1)
    assert not cleaned_1.startswith("Quan trọng:")
    assert "DUSN-X có các tính năng cốt lõi" in cleaned_1

    leaked_output_2 = (
        "CRITICAL MANDATORY INSTRUCTION: You MUST write your ENTIRE response in ENGLISH ONLY.\n"
        "Continuous integration allows developers to integrate code changes frequently."
    )
    cleaned_2 = sanitize_generated_reply(leaked_output_2)
    assert "CRITICAL MANDATORY INSTRUCTION" not in cleaned_2
    assert "Continuous integration" in cleaned_2


def test_sanitize_removes_correction_meta_commentary():
    text = ("Thủ đô của Pháp là Paris.\n\n"
            "Câu này đã được viết bằng tiếng Việt để đáp ứng yêu cầu người dùng, "
            "không sao chép bản nháp lỗi trước đó hoặc trộn ngôn ngữ như trong lần sửa đổi đầu tiên.")
    cleaned = sanitize_generated_reply(text)
    assert "Thủ đô của Pháp là Paris." in cleaned
    assert "bản nháp" not in cleaned


def test_quality_flags_detector_and_false_positive_resistance():
    """Quality flags detector catches leaks and loops, but ignores legitimate text."""
    # 1. Obvious leak must be flagged
    leaked_text = "Quan trọng: - Trả lời trực tiếp câu hỏi dựa trên trí nhớ hiệu lực."
    assert "system_instruction_leak" in quality_flags(leaked_text)

    # 2. Repeated lines must be flagged
    repeated_text = "\n".join(["Tối ưu hóa hiệu suất hệ thống."] * 5)
    assert "repeated_lines" in quality_flags(repeated_text)

    # 3. Legitimate conversational text must NOT be flagged (no false positives)
    legit_vi = (
        "Hệ thống DUSN-X có 4 tính năng cốt lõi chính: quản lý trí nhớ dài hạn, "
        "định tuyến tác vụ đa tác tử, phân tích dữ liệu và tích hợp Office."
    )
    assert quality_flags(legit_vi) == []

    legit_en = (
        "Continuous integration improves team velocity and detects integration bugs early "
        "by executing automated regression test suites on every commit."
    )
    assert quality_flags(legit_en) == []
