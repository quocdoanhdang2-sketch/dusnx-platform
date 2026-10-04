from apps.ai_api.language import detect_language, preference_instruction, response_language
from apps.ai_api import main, provider
from test_week2_acceptance import client, isolated_week2_env, _register_and_login


def test_language_detection_policy():
    assert detect_language("API này đang dùng cache nào?") == "vi"
    assert detect_language("Which cache does this API use?") == "en"
    assert detect_language("Yes", previous="en") == "en"
    assert detect_language("Có", previous="vi") == "vi"
    assert response_language("en", "vi") == "en"
    assert response_language("vi", "en") == "vi"
    assert preference_instruction("Từ giờ trả lời bằng tiếng Anh.") == "en"
    assert preference_instruction("Please answer in Vietnamese from now on.") == "vi"


def test_language_preference_persists_and_is_isolated(client):
    _, token_a = _register_and_login(client, "postw4_lang_a")
    _, token_b = _register_and_login(client, "postw4_lang_b")
    ha, hb = ({"Authorization": f"Bearer {token_a}"}, {"Authorization": f"Bearer {token_b}"})
    sid = client.post("/v1/sessions", headers=ha, json={"title": "Language"}).json()["session_id"]
    saved = client.post("/v1/chat", headers=ha, json={"session_id": sid,
        "message": "Từ giờ trả lời bằng tiếng Anh.", "request_id": "language-pref-001"})
    assert saved.status_code == 200
    assert saved.json()["response_language"] == "en"
    assert any(m["content"] == "language:en" for m in client.get("/v1/memories", headers=ha).json())
    assert not client.get("/v1/memories", headers=hb).json()


def test_inspector_off_by_default_and_safe_when_enabled(client, monkeypatch):
    monkeypatch.setattr(main, "generate_response", lambda **kwargs:
        provider.ProviderResult("Safe", True, "mock", "mock-model", 1, called=True))
    _, token = _register_and_login(client, "postw4_inspector")
    h = {"Authorization": f"Bearer {token}"}
    sid = client.post("/v1/sessions", headers=h, json={"title": "Inspector"}).json()["session_id"]
    off = client.post("/v1/chat", headers=h, json={"session_id": sid, "message": "Explain this",
        "request_id": "inspector-off-01"}).json()
    assert off["inspector"] is None
    monkeypatch.setenv("DUSNX_ENABLE_INSPECTOR", "1")
    on = client.post("/v1/chat", headers=h, json={"session_id": sid, "message": "Explain more",
        "request_id": "inspector-on-001"}).json()
    assert on["inspector"]["model_used"] == "mock-model"
    serialized = str(on["inspector"]).casefold()
    assert "authorization" not in serialized and "bearer" not in serialized and "system_prompt" not in serialized
