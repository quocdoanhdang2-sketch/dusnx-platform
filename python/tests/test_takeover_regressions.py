import json
from io import BytesIO

from apps.ai_api import provider
from apps.ai_api.main import _detect_project_scoped_question
from verify_real_ollama_week2 import check_final


def test_provider_preserves_history_and_measures_only_reported_metadata(monkeypatch):
    monkeypatch.setenv("DUSNX_PROVIDER", "ollama")
    captured = []
    def urlopen(request, timeout):
        captured.append(json.loads(request.data))
        return BytesIO(json.dumps({"done": True, "message": {"content": "MongoDB"}, "model": "qwen-test", "eval_count": 9}).encode())
    monkeypatch.setattr(provider.urllib.request, "urlopen", urlopen)
    text, ok, source, model, count = provider.generate_response(
        "Câu hỏi", [], "chat", [{"role": "user", "content": "past context"}])
    assert (text, ok, source, model, count) == ("MongoDB", True, "ollama", "qwen-test", 9)
    assert "past context" in captured[0]["messages"][0]["content"]
    assert captured[0]["messages"][1]["content"] == "Câu hỏi"
    monkeypatch.setattr(provider.urllib.request, "urlopen", lambda *a, **k: BytesIO(b'{"message":{"content":"ok"}}'))
    assert provider._ollama_generate("system", "user")[2:] == (None, None)


def test_mock_never_claims_measured_llm_tokens(monkeypatch):
    monkeypatch.setenv("DUSNX_PROVIDER", "mock")
    assert provider.generate_response("hello", [], "chat")[3:] == (None, None)


def test_ollama_health_requires_exact_model_tag(monkeypatch):
    monkeypatch.setenv("DUSNX_OLLAMA_MODEL", "qwen2.5:0.5b")
    monkeypatch.setattr(provider.urllib.request, "urlopen", lambda *a, **k: BytesIO(
        b'{"models":[{"name":"qwen2.5:7b"}]}'))
    assert provider.check_ollama_health()["available"] is False


def test_empty_provider_reply_is_not_success(monkeypatch):
    monkeypatch.setattr(provider.urllib.request, "urlopen", lambda *a, **k: BytesIO(b'{"message":{"content":""}}'))
    assert provider._ollama_generate("system", "user")[1] is False


def test_project_guard_does_not_block_general_questions():
    assert not _detect_project_scoped_question("Python là gì?", "project-alpha")
    assert _detect_project_scoped_question("Database của dự án này là gì?", "project-alpha")
    assert not _detect_project_scoped_question("Database của dự án này là gì?", None)


def test_http_acceptance_requires_real_provider_and_actual_supersession():
    memories = [{"memory_id": "old", "content": "PostgreSQL", "is_active": False},
                {"memory_id": "new", "content": "MongoDB", "is_active": True}]
    reply = {"reply": "MongoDB", "provider_ok": True, "provider_used": None, "provider_called": False,
             "response_source": "grounded_template", "model_used": None, "memory_ids_used": ["new"]}
    assert all(check_final(reply, memories, "old").values())
    assert not check_final(reply, memories[1:], "old")["postgresql_superseded"]
    reply["provider_used"] = "mock"
    assert not check_final(reply, memories, "old")["grounded_source"]
    reply["provider_used"] = None
    reply["reply"] = "PostgreSQL, MongoDB"
    assert not check_final(reply, memories, "old")["answer_mongodb_only"]
