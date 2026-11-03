"""Regressions for project preference writes and empty post-sanitizer replies."""
import pytest
from test_week2_acceptance import _register_and_login
from test_week2_acceptance import client as client  # noqa: PLC0414 -- pytest fixture re-export
from test_week2_acceptance import isolated_week2_env as isolated_week2_env  # noqa: PLC0414

from apps.ai_api import provider
from apps.ai_api.memory import get_memory_db


def test_project_language_write_never_supersedes_global_or_other_project(client):
    _, token = _register_and_login(client, "scoped_language_write")
    headers = {"Authorization": f"Bearer {token}"}
    uid = client.get("/v1/auth/me", headers=headers).json()["user_id"]
    sid = client.post("/v1/sessions", headers=headers, json={}).json()["session_id"]
    projects = [client.post("/v1/projects", headers=headers, json={"name": name}).json()["project_id"]
                for name in ("Synthetic A", "Synthetic B")]
    db = get_memory_db()

    def change(language, project=None):
        response = client.post("/v1/chat", headers=headers, json={
            "session_id": sid, "project_id": project,
            "message": "Từ giờ trả lời bằng tiếng " + ("Anh." if language == "en" else "Việt.")})
        assert response.status_code == 200
        assert response.json()["intent"] == "set_language_preference"
        return response.json()["memory_ids_used"][0]

    global_id = change("vi")
    project_a_id = change("en", projects[0])
    assert db.get_memory(uid, global_id)["is_active"]
    assert db.get_memory(uid, global_id)["content"] == "language:vi"
    assert db.get_memory(uid, project_a_id)["project_id"] == projects[0]
    assert db.get_language_preference(uid) == "vi"
    assert db.get_language_preference(uid, projects[0]) == "en"
    assert db.get_language_preference(uid, projects[1]) == "vi"

    project_b_id = change("en", projects[1])
    revised_a_id = change("vi", projects[0])
    assert not db.get_memory(uid, project_a_id)["is_active"]
    assert db.get_memory(uid, revised_a_id)["project_id"] == projects[0]
    assert db.get_memory(uid, project_b_id)["is_active"]
    assert db.get_memory(uid, global_id)["is_active"]
    change("en")
    assert db.get_language_preference(uid) == "en"
    assert db.get_language_preference(uid, projects[0]) == "vi"
    assert db.get_language_preference(uid, projects[1]) == "en"
    assert change("vi", projects[0]) == revised_a_id  # No duplicate for unchanged value.


@pytest.mark.parametrize("kind", ["ollama", "openai"])
@pytest.mark.parametrize("raw", ["Quan trọng:", "Rules:", "Instructions:", " \n "])
def test_empty_sanitized_reply_is_provider_failure(monkeypatch, kind, raw):
    monkeypatch.setenv("DUSNX_PROVIDER", kind)
    monkeypatch.setattr(provider, "OPENAI_API_KEY", "synthetic-not-a-credential")
    monkeypatch.setattr(provider, "_" + kind + "_generate", lambda *args:
                        (raw, True, "synthetic-model", 2))
    result = provider.generate_response("Explain rainbows.", [], "chat", response_language="en")
    assert not result[1]
    assert "empty_response" in result[0]
    assert result[2] == kind
    assert result[3:] == (None, None)
    assert result.provider_called is True


@pytest.mark.parametrize("kind", ["ollama", "openai"])
def test_empty_reply_is_not_saved_and_same_request_can_retry(client, monkeypatch, kind):
    monkeypatch.setenv("DUSNX_PROVIDER", kind)
    monkeypatch.setattr(provider, "OPENAI_API_KEY", "synthetic-not-a-credential")
    outputs = iter(["Quan trọng:", "A rainbow forms when light passes through water droplets."])
    monkeypatch.setattr(provider, "_" + kind + "_generate", lambda *args:
                        (next(outputs), True, "synthetic-model", 8))
    _, token = _register_and_login(client, "empty_reply_retry_" + kind)
    headers = {"Authorization": f"Bearer {token}"}
    sid = client.post("/v1/sessions", headers=headers, json={}).json()["session_id"]
    payload = {"session_id": sid, "message": "Explain how a rainbow forms.",
               "request_id": "synthetic-empty-reply", "preferred_language": "en"}
    response = client.post("/v1/chat", headers=headers, json=payload)
    assert response.status_code == 200
    first = response.json()
    assert first["provider_ok"] is False
    assert first["provider_called"] is True
    assert first["response_source"] == "provider_error"
    assert "empty_response" in first["reply"]
    messages = client.get(f"/v1/sessions/{sid}/messages", headers=headers).json()
    assert len(messages) == 1 and messages[0]["role"] == "user"
    response = client.post("/v1/chat", headers=headers, json={**payload, "is_retry": True})
    assert response.status_code == 200
    assert response.json()["provider_ok"] is True
    assert response.json()["response_source"] == "llm"  # Mocked transport, not live generation.
    messages = client.get(f"/v1/sessions/{sid}/messages", headers=headers).json()
    assert [m["role"] for m in messages] == ["user", "assistant"]
    assert messages[1]["content"] == "A rainbow forms when light passes through water droplets."
