"""Provider routing: trained local model primary, external API fallback/compare."""
import pytest

from apps.ai_api import provider


def _result(text, ok=True, provider_used="ollama", model=None, tokens=None):
    # Transport-level fake: generate_response unpacks (text, ok, model, tokens).
    return provider.ProviderCall(text, ok, model, tokens)


@pytest.fixture(autouse=True)
def _isolate_provider_env(monkeypatch):
    monkeypatch.setenv("DUSNX_PROVIDER", "ollama")
    monkeypatch.setenv("DUSNX_PROVIDER_FALLBACK", "openai")
    monkeypatch.setattr(provider, "OPENAI_API_KEY", "test-key")
    monkeypatch.setattr(provider, "OPENAI_MODEL", "gemini-test")


def test_provider_override_targets_external_api(monkeypatch):
    calls = []

    def fake_openai(system_prompt, user_message):
        calls.append(user_message)
        return _result("Câu trả lời từ API.", True, "openai", "gemini-test", 7)

    monkeypatch.setattr(provider, "_openai_generate", fake_openai)
    monkeypatch.setattr(provider, "get_current_provider", lambda: "ollama")
    text, ok, used, model, tokens = provider.generate_response(
        "Quỹ CLB đóng khi nào?", [], "chat", response_language="vi",
        provider_override="openai")
    assert ok and used == "openai" and model == "gemini-test" and tokens == 7
    assert text == "Câu trả lời từ API."
    assert calls == ["Quỹ CLB đóng khi nào?"] or "Quỹ CLB đóng khi nào?" in calls[0]


def test_ollama_failure_falls_back_to_external_api(monkeypatch):
    monkeypatch.setattr(provider, "get_current_provider", lambda: "ollama")
    monkeypatch.setattr(provider, "_ollama_generate",
                        lambda system_prompt, user_message: _result(
                            "[Ollama service error (unreachable)]", False, "ollama", None, None))
    monkeypatch.setattr(provider, "_openai_generate",
                        lambda system_prompt, user_message: _result(
                            "Trả lời dự phòng.", True, "openai", "gemini-test", 5))
    text, ok, used, model, tokens = provider.generate_response(
        "Lịch sinh hoạt CLB?", [], "chat", response_language="vi")
    assert ok and used == "openai" and model == "gemini-test" and tokens == 5
    assert text == "Trả lời dự phòng."


def test_mock_reports_no_fabricated_model_or_tokens(monkeypatch):
    monkeypatch.setenv("DUSNX_PROVIDER", "mock")
    text, ok, used, model, tokens = provider.generate_response(
        "Xin chào", [], "chat", response_language="vi")
    assert ok and used == "mock"
    assert model is None and tokens is None
