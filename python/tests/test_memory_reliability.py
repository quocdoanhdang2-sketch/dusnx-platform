"""Regressions found in long conversations and existing SQLite accounts."""
import hashlib
import secrets

from apps.ai_api import main, provider
from apps.ai_api.auth import get_auth_db
from apps.ai_api.memory import get_memory_db
from test_week2_acceptance import client, isolated_week2_env, _register_and_login


def test_long_session_uses_latest_context_and_retry_does_not_duplicate(client, monkeypatch):
    _, token = _register_and_login(client, "recent_context_regression")
    headers = {"Authorization": f"Bearer {token}"}
    user = client.get("/v1/auth/me", headers=headers).json()
    sid = client.post("/v1/sessions", headers=headers, json={}).json()["session_id"]
    db = get_memory_db()
    for i in range(16):
        db.append_message(sid, user["user_id"], "user" if i % 2 == 0 else "assistant", f"turn-{i}")
    captured = []
    def offline(**kwargs):
        captured.append(kwargs["session_history"])
        return provider.ProviderResult("unreachable", False, "ollama", None, None, called=True)
    monkeypatch.setattr(main, "generate_response", offline)
    payload = {"session_id": sid, "message": "Explain a new concept", "request_id": secrets.token_hex(16)}
    first = client.post("/v1/chat", headers=headers, json=payload).json()
    assert first["provider_ok"] is False
    assert captured[0][-1]["content"] == "turn-15"
    assert captured[0][0]["content"] == "turn-5"
    client.post("/v1/chat", headers=headers, json={**payload, "is_retry": True})
    messages = db.get_messages(user["user_id"], sid)
    assert sum(m["content"] == payload["message"] for m in messages) == 1


def test_memory_history_follows_links_not_coincident_timestamps(client, monkeypatch):
    import apps.ai_api.memory as memory
    monkeypatch.setattr(memory, "_now", lambda: "2026-10-31T00:00:00+00:00")
    db = get_memory_db()
    first = db.create_memory("synthetic-owner", "decision", "First independent fact")
    unrelated = db.create_memory("synthetic-owner", "decision", "Unrelated fact")
    updated = db.update_memory("synthetic-owner", first["memory_id"], "Updated fact")
    for mid in (first["memory_id"], updated["memory_id"]):
        history = db.get_memory_history("synthetic-owner", mid)
        assert [m["memory_id"] for m in history] == [first["memory_id"], updated["memory_id"]]
        assert unrelated["memory_id"] not in {m["memory_id"] for m in history}
    assert db.get_memory_history("other-owner", updated["memory_id"]) == []


def test_existing_password_is_upgraded_only_after_successful_login(client):
    db = get_auth_db()
    password = secrets.token_urlsafe(24)
    user = db.register("legacy_hash_regression", password)
    row = db._conn.execute("SELECT * FROM users WHERE user_id=?", (user["user_id"],)).fetchone()
    assert row["password_hash"].startswith("scrypt$")
    legacy = hashlib.sha256((row["salt"] + password).encode()).hexdigest()
    db._conn.execute("UPDATE users SET password_hash=? WHERE user_id=?", (legacy, user["user_id"]))
    db._conn.commit()
    assert db.login(user["username"], secrets.token_urlsafe(24)) is None
    assert db._conn.execute("SELECT password_hash FROM users WHERE user_id=?", (user["user_id"],)).fetchone()[0] == legacy
    assert db.login(user["username"], password)
    assert db._conn.execute("SELECT password_hash FROM users WHERE user_id=?", (user["user_id"],)).fetchone()[0].startswith("scrypt$")
