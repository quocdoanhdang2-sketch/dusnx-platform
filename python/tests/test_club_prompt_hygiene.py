"""Prompt-hygiene regressions for the club assistant.

The 0.5B club LoRA echoes instruction text when the prompt is
instruction-heavy: the first CASE-13 acceptance run answered

    Chào bạn! Câu hỏi của bạn là 'Hãy trả lời bằng tiếng Việt'.

These tests pin the two independent guards that keep that text out of the UI:

* a bare greeting/thanks goes to the model with a minimal prompt, so the
  answer is genuinely generated instead of a canned string;
* ``sanitize_generated_reply`` still strips instruction echo from any provider
  output, as a safety net.

They also pin the capability-question regex so a lookup such as "Bạn có biết
chủ nhiệm CLB là ai không?" reaches RAG instead of the capability card.
"""
from apps.ai_api import main, provider


def test_capability_question_matches_identity_and_help_forms():
    for question in (
        "Bạn là ai?",
        "Bạn tên là gì?",
        "Bạn làm được gì?",
        "Bạn có thể làm gì?",
        "Chức năng của bạn là gì?",
        "Bạn biết gì?",
    ):
        assert main._CAPABILITY_QUESTION.search(question), question


def test_capability_question_does_not_hijack_domain_lookups():
    for question in (
        "Bạn có biết chủ nhiệm CLB là ai không?",
        "Bạn cho tôi biết trưởng ban kỹ thuật là ai?",
        "Bạn biết gì về CLB IT?",
        "Trưởng ban truyền thông là người nào?",
    ):
        assert not main._CAPABILITY_QUESTION.search(question), question


def test_small_talk_matches_only_bare_greetings_and_thanks():
    for message in (
        "Cảm ơn bạn rất nhiều!",
        "cảm ơn nhé",
        "Chào bạn!",
        "Xin chào",
        "Hello",
        "Thank you!",
    ):
        assert provider._SMALL_TALK.match(message), message
    for message in (
        "Chào bạn, lịch sinh hoạt CLB thế nào?",
        "Cảm ơn bạn. Cho tôi hỏi quy định phòng lab?",
        "Quy định sử dụng phòng lab của CLB là gì?",
        "Cảm ơn bạn đã giải thích, nhưng quỹ CLB đóng bao nhiêu một tháng?",
    ):
        assert not provider._SMALL_TALK.match(message), message


def test_sanitizer_removes_instruction_echo():
    leaked = "Chào bạn! Câu hỏi của bạn là 'Hãy trả lời bằng tiếng Việt'."
    cleaned = provider.sanitize_generated_reply(leaked)
    assert "Hãy trả lời" not in cleaned
    assert "Câu hỏi của bạn là" not in cleaned
    assert "Chào bạn" in cleaned


def test_small_talk_call_uses_light_prompt_and_user_text(monkeypatch):
    captured = {}

    def fake_generate(system_prompt: str, user_message: str) -> provider.ProviderCall:
        captured["system"] = system_prompt
        captured["user"] = user_message
        captured["greedy"] = provider._SMALL_TALK_CALL.get()
        return provider.ProviderCall(
            "Rất vui được hỗ trợ bạn! Nếu cần thêm thông tin, bạn cứ nhắn mình nhé.",
            True, "dusnx-vi-club", 14)

    monkeypatch.setattr(provider, "_ollama_generate", fake_generate)
    text, ok, provider_used, model_used, _tokens = provider.generate_response(
        "Cảm ơn bạn rất nhiều!",
        [],
        "smalltalk",
        response_language="vi",
        provider_override="ollama",
        allow_fallback=False,
    )
    assert ok and provider_used == "ollama" and model_used == "dusnx-vi-club"
    assert text.startswith("Rất vui được hỗ trợ")
    assert captured["user"] == "Cảm ơn bạn rất nhiều!"
    assert captured["greedy"] is True
    assert "Hãy trả lời bằng tiếng Việt" not in captured["system"]
    assert "Hoàn thành yêu cầu" not in captured["system"]


def test_sanitizer_removes_training_loop_narration():
    leaked = ("Câu trả lời lần 1 đã không đạt kiểm tra. Xin hãy viết lại từ đầu.\n"
              "Không có gì, rất vui được giúp bạn!")
    cleaned = provider.sanitize_generated_reply(leaked)
    assert "không đạt kiểm tra" not in cleaned.lower()
    assert "viết lại từ đầu" not in cleaned.lower()
    assert "Không có gì" in cleaned


def test_unusable_small_talk_reply_falls_back_honestly(monkeypatch):
    def fake_generate(system_prompt: str, user_message: str) -> provider.ProviderCall:
        # Sampling drift observed from the real 0.5B LoRA.
        return provider.ProviderCall("Rất vui được giúp bạn! 还需要什么吗?", True,
                                     "dusnx-vi-club", 12)

    monkeypatch.setattr(provider, "_ollama_generate", fake_generate)
    generated = provider.generate_response(
        "Cảm ơn bạn rất nhiều!",
        [],
        "smalltalk",
        response_language="vi",
        provider_override="ollama",
        allow_fallback=False,
    )
    text, ok, provider_used, model_used, tokens = generated
    assert ok and provider_used == "ollama"
    assert text == provider.SMALL_TALK_FALLBACKS["thanks"]
    assert generated.provider_called is True
    assert generated.response_source == "template"
    assert model_used is None and tokens is None


def test_regular_question_keeps_grounded_prompt(monkeypatch):
    captured = {}

    def fake_generate(system_prompt: str, user_message: str) -> provider.ProviderCall:
        captured["system"] = system_prompt
        captured["user"] = user_message
        captured["greedy"] = provider._SMALL_TALK_CALL.get()
        return provider.ProviderCall("Câu trả lời có trích dẫn [S1].", True,
                                     "dusnx-vi-club", 9)

    monkeypatch.setattr(provider, "_ollama_generate", fake_generate)
    provider.generate_response(
        "Quy định sử dụng phòng lab của CLB là gì?",
        [],
        "question",
        response_language="vi",
        knowledge_context="[S1] Quy định phòng lab...",
        provider_override="ollama",
        allow_fallback=False,
    )
    assert "[S1] Quy định phòng lab" in captured["system"]
    assert "Yêu cầu người dùng:" in captured["user"]
    assert captured["greedy"] is False
