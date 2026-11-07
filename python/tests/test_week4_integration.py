"""Regressions for actual Week 4 failure causes; runtime evidence is separate."""
import json
from io import BytesIO
import urllib.error

import pytest
from apps.ai_api import provider, main
from test_week2_acceptance import isolated_week2_env, client, _register_and_login


@pytest.mark.parametrize("raw,category", [
    (b"not json", "invalid_json"),
    (b'[]', "invalid_schema"),
    (b'{"done":true,"model":"qwen","message":{"content":5}}', "invalid_schema"),
    (b'{"done":false,"model":"qwen","message":{"content":"partial"}}', "incomplete_response"),
])
def test_provider_rejects_malformed_without_retry_or_leak(monkeypatch, raw, category):
    calls = []
    def response(req, timeout):
        calls.append(req.full_url)
        return BytesIO(raw)
    monkeypatch.setattr(provider.urllib.request, "urlopen", response)
    text, ok, model, tokens = provider._ollama_generate("context", "question")
    assert not ok and category in text
    assert model == ("qwen" if b'"model":"qwen"' in raw else None)
    # A malformed chat response must not be retried. Model discovery
    # (GET /api/tags) is a separate lookup, not a generation attempt.
    assert len([url for url in calls if url.endswith("/api/chat")]) == 1


def test_qwen_thinking_only_response_is_empty_content_with_metadata(monkeypatch):
    raw = json.dumps({"done": True, "done_reason": "length", "model": "qwen3:4b",
                      "eval_count": 512, "prompt_eval_count": 42,
                      "message": {"role": "assistant", "content": "", "thinking": "private reasoning"}}).encode()
    monkeypatch.delenv("DUSNX_CAPTURE_RAW_GENERATION", raising=False)
    monkeypatch.setattr(provider.urllib.request, "urlopen", lambda req, timeout: BytesIO(raw))
    result = provider._ollama_generate("system", "user")
    assert not result[1] and "empty_content" in result[0]
    assert result[2:] == ("qwen3:4b", 512)
    assert result.done_reason == "length"
    assert "n\u1ed9i dung r\u1ed7ng" in result[0]
    assert result.diagnostics["thinking_chars"] == len("private reasoning")
    assert "private reasoning" not in result.diagnostics
    assert result.diagnostics["num_predict"] == 512
    assert result.diagnostics["response_sha256"]
    assert result.diagnostics["response_classification"] == "thinking_only_budget_exhausted"
    assert result.diagnostics["token_budget_status"] == "reached"
    assert result.diagnostics["schema_valid"] is True
    assert result.diagnostics["http_completed"] is True
    assert result.diagnostics["error_category"] == "empty_content"


def test_provider_budget_diagnostic_is_unknown_without_eval_metadata(monkeypatch):
    raw = json.dumps({"done": True, "done_reason": "stop", "model": "qwen3:4b",
                      "message": {"content": "Answer."}}).encode()
    monkeypatch.setattr(provider.urllib.request, "urlopen", lambda req, timeout: BytesIO(raw))
    result = provider._ollama_generate("system", "user")
    assert result[1] is True
    assert result.diagnostics["token_budget_status"] == "unknown"


@pytest.mark.parametrize("error", [
    TimeoutError("http://user:password@host/?token=secret"),
    urllib.error.URLError(TimeoutError("http://user:password@host/?token=secret")),
])
def test_provider_diagnostics_mark_direct_and_wrapped_timeout_without_exception_details(monkeypatch, error):
    monkeypatch.setattr(provider.urllib.request, "urlopen", lambda req, timeout: (_ for _ in ()).throw(error))
    result = provider._ollama_generate("synthetic system", "synthetic request")
    assert result.diagnostics["error_category"] == "timeout"
    assert result.diagnostics["validation"] == "timeout"
    assert result.diagnostics["http_completed"] is False
    serialized = json.dumps(result.diagnostics)
    assert "password" not in serialized and "secret" not in serialized


def test_qwen_content_and_thinking_raw_capture_is_explicit(monkeypatch):
    raw = json.dumps({"done": True, "done_reason": "stop", "model": "qwen3:4b",
                      "eval_count": 9, "message": {"content": "Trả lời.", "thinking": "reason"}}).encode()
    monkeypatch.setenv("DUSNX_CAPTURE_RAW_GENERATION", "1")
    monkeypatch.setattr(provider.urllib.request, "urlopen", lambda req, timeout: BytesIO(raw))
    result = provider._ollama_generate("system", "user")
    assert result[0] == "Trả lời." and result[1]
    assert result.diagnostics["done_reason"] == "stop"
    assert result.diagnostics["content"] == "Trả lời."
    assert result.diagnostics["thinking"] == "reason"


def test_provider_http_failure_does_not_expose_secret_url(monkeypatch):
    def failure(req, timeout):
        raise urllib.error.HTTPError("http://secret:password@host/?token=private", 404, "private", {}, None)
    monkeypatch.setattr(provider.urllib.request, "urlopen", failure)
    text, ok, _, _ = provider._ollama_generate("context", "question")
    assert not ok and "model_missing" in text and "private" not in text and "password" not in text


def test_relative_checkpoint_is_rooted_at_repository(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("DUSNX_CHECKPOINT", "artifacts/example.pt")
    assert main.resolve_default_checkpoint() == str((main.ARTIFACT_ROOT / "artifacts/example.pt").resolve())


def test_durable_chat_replay_does_not_repeat_mutation(client):
    _, token = _register_and_login(client, "week4_receipt")
    h = {"Authorization": f"Bearer {token}"}
    sid = client.post("/v1/sessions", headers=h, json={"title": "Receipt"}).json()["session_id"]
    payload = dict(session_id=sid, message="Hãy nhớ rằng tôi thích trà sen.", request_id="week4-save-001")
    first = client.post("/v1/chat", headers=h, json=payload)
    assert first.status_code == 200 and first.json()["intent"] == "memory_create"
    before = client.get("/v1/me/state", headers=h).json()
    replay = client.post("/v1/chat", headers=h, json={**payload, "is_retry": True})
    assert replay.json()["message_id"] == first.json()["message_id"]
    assert replay.json()["reply"] == first.json()["reply"] and replay.json()["replayed"]
    assert replay.json()["response_source"] == "replay" and not replay.json()["provider_called"]
    assert client.get("/v1/me/state", headers=h).json() == before
    assert len(client.get("/v1/memories", headers=h).json()) == 1
    assert len(client.get(f"/v1/sessions/{sid}/messages", headers=h).json()) == 2
    conflict = client.post("/v1/chat", headers=h, json={**payload, "message": "Hãy nhớ rằng tôi thích cà phê."})
    assert conflict.status_code == 409


def test_direct_update_cannot_fork_inactive_memory(client):
    _, token = _register_and_login(client, "week4_update")
    h = {"Authorization": f"Bearer {token}"}
    original = client.post("/v1/memories", headers=h, json={"info_type": "decision", "content": "Chọn trà sen."}).json()
    mid = original["memory_id"]
    first = client.put(f"/v1/memories/{mid}", headers=h, json={"content": "Chọn trà đào."})
    assert first.status_code == 200 and first.json()["version"] == 2
    assert client.put(f"/v1/memories/{mid}", headers=h, json={"content": "Chọn cà phê."}).status_code == 404
    active = client.get("/v1/memories", headers=h).json()
    assert len(active) == 1 and active[0]["content"] == "Chọn trà đào."


def test_llm_replay_reports_no_new_provider_call(client, monkeypatch):
    calls = []
    def generate(**kwargs):
        calls.append(kwargs)
        return provider.ProviderResult("Một câu đã sinh.", True, "ollama", "test-model", 5, called=True)
    monkeypatch.setattr(main, "generate_response", generate)
    _, token = _register_and_login(client, "week4_llm_replay")
    h = {"Authorization": f"Bearer {token}"}
    sid = client.post("/v1/sessions", headers=h, json={"title": "Replay"}).json()["session_id"]
    payload = dict(session_id=sid, message="Viết một câu về đọc sách.", request_id="llm-replay-001")
    original = client.post("/v1/chat", headers=h, json=payload).json()
    repeated = client.post("/v1/chat", headers=h, json=payload).json()
    assert len(calls) == 1 and original["provider_called"] and original["response_source"] == "llm"
    assert repeated["message_id"] == original["message_id"] and repeated["reply"] == original["reply"]
    assert repeated["response_source"] == "replay" and not repeated["provider_called"]
    assert repeated["provider_used"] is None and repeated["model_used"] is None
    assert repeated["original_provenance"]["model_used"] == "test-model"


def test_direct_update_rolls_back_on_deactivation_failure(client):
    from apps.ai_api.memory import get_memory_db
    _, token = _register_and_login(client, "week4_rollback")
    h = {"Authorization": f"Bearer {token}"}
    original = client.post("/v1/memories", headers=h, json={"info_type": "decision", "content": "Chọn trà sen."}).json()
    db = get_memory_db()
    db._conn.execute("CREATE TRIGGER fail_direct_update BEFORE UPDATE OF is_active ON memories BEGIN SELECT RAISE(ABORT,'test rollback'); END")
    db._conn.commit()
    try:
        with pytest.raises(Exception, match="test rollback"):
            db.update_memory(original["user_id"], original["memory_id"], "Chọn trà đào.")
        memories = client.get("/v1/memories?include_inactive=true", headers=h).json()
        assert memories == [original]
    finally:
        db._conn.execute("DROP TRIGGER fail_direct_update")
        db._conn.commit()


def test_corrupt_state_is_visible_and_rejected_without_silent_reload(client):
    from apps.ai_api.memory import get_memory_db
    _, token = _register_and_login(client, "week4_corrupt_state")
    h = {"Authorization": f"Bearer {token}"}
    uid = client.get("/v1/auth/me", headers=h).json()["user_id"]
    db = get_memory_db()
    db.set_dusnx_state(uid, {"global_state": "invalid"}, 5)
    visible = client.get("/v1/me/state", headers=h).json()
    assert visible["state_compatible"] is False and visible["reset_reason"] == "invalid_state_schema"
    failed = client.post("/v1/me/events", headers=h, json={"platform": "web", "content": "state safety"})
    assert failed.status_code == 409
    assert db.get_dusnx_state(uid)["state_version"] == 5
    assert client.get("/v1/me/events", headers=h).json()["events"] == []
