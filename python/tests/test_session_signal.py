"""Tests for deterministic work-session encoding (no model, no database)."""
from dusnx_core import session_signal as signal


def test_classify_intent_covers_the_work_signals():
    assert signal.classify_intent("Gateway chạy ở cổng nào?") == "question"
    assert signal.classify_intent("viết giúp đoạn mô tả release") == "instruction"
    assert signal.classify_intent("sửa lại phần đăng nhập") == "correction"
    assert signal.classify_intent("sai rồi, không phải 8080") == "correction"
    assert signal.classify_intent("ok") == "approval"
    assert signal.classify_intent("nhớ rằng tao dùng Qwen 1.5B") == "memory_write"
    assert signal.classify_intent("hôm nay trời đẹp") == "statement"
    assert signal.classify_intent("anything", role="assistant") == "statement"


def test_extract_entities_finds_paths_ports_env_and_commands():
    text = ("Chạy node word-addin/dev-server.js rồi mở https://localhost:3001, "
            "đặt WORD_ADDIN_PORT=3001 và kiểm tra python/data/memory.db")
    entities = signal.extract_entities(text)
    assert "word-addin/dev-server.js" in entities["path"]
    assert "python/data/memory.db" in entities["path"]
    assert "3001" in entities["port"]
    assert "WORD_ADDIN_PORT" in entities["env"]
    assert any("node word-addin/dev-server.js" in command for command in entities["command"])


def test_scrub_removes_secrets_before_storage():
    raw = "gửi tới student@example.com với sk-abcdefghijklmnop và hash " + "a" * 40
    cleaned = signal.scrub(raw)
    assert "student@example.com" not in cleaned
    assert "sk-abcdefghijklmnop" not in cleaned
    assert "a" * 40 not in cleaned
    assert cleaned.count("[REDACTED") == 3


def test_classify_outcome_marks_refusal_and_error():
    assert signal.classify_outcome("Xin lỗi, mình không tìm thấy dữ liệu.", "assistant") == "refused"
    assert signal.classify_outcome("Lỗi: không kết nối được Gateway.", "assistant") == "error"
    assert signal.classify_outcome("Gateway chạy ở cổng 8080.", "assistant") == "answered"
    assert signal.classify_outcome("câu hỏi", "user") == "not_applicable"


def test_record_is_content_free_and_deterministic():
    messages = [
        {"role": "user", "content": "Gateway chạy ở cổng nào?"},
        {"role": "assistant", "content": "Gateway mặc định ở cổng 8080."},
        {"role": "user", "content": "sai rồi, đổi sang 8181"},
    ]
    first = signal.encode_session(messages).as_record(session_id="s1")
    second = signal.encode_session(messages).as_record(session_id="s1")
    assert first == second
    assert first["has_correction"] is True
    assert first["intents"] == {"correction": 1, "question": 1, "statement": 1}
    assert first["outcomes"]["answered"] == 1
    assert "content" not in first
    assert len(first["signature"]) == 16
