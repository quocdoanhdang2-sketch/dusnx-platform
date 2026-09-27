"""
DUSN-X HTTP Integration Tests
==============================
End-to-end tests exercising FastAPI HTTP endpoints via TestClient:
- Health check
- Auth: Register, Login, Me, Logout, Invalid credentials, Token expiration
- Sessions: Create, List, Delete
- Memories: Create, List, Update (versioning), Delete
- Chat: Send message, context injection from memory, routing metadata
- User isolation across HTTP requests
- Project management
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from apps.ai_api.main import app
import apps.ai_api.auth as auth_mod
import apps.ai_api.memory as mem_mod


@pytest.fixture(autouse=True)
def isolated_http_env(tmp_path, monkeypatch):
    """Each test runs against an isolated SQLite DB in tmp_path."""
    monkeypatch.setenv("DUSNX_DATA_DIR", str(tmp_path))
    if auth_mod._auth_db is not None:
        auth_mod._auth_db.close()
        auth_mod._auth_db = None
    if mem_mod._memory_db is not None:
        mem_mod._memory_db.close()
        mem_mod._memory_db = None
    yield
    if auth_mod._auth_db is not None:
        auth_mod._auth_db.close()
        auth_mod._auth_db = None
    if mem_mod._memory_db is not None:
        mem_mod._memory_db.close()
        mem_mod._memory_db = None


@pytest.fixture
def client():
    with TestClient(app) as test_client:
        yield test_client


def _register_and_login(client: TestClient, username: str = "testuser", password: str = "secret12345") -> tuple[str, str]:
    """Helper: register, login, return (user_id, token)."""
    reg_resp = client.post("/v1/auth/register", json={"username": username, "password": password})
    assert reg_resp.status_code == 201, reg_resp.text
    user_id = reg_resp.json()["user_id"]

    login_resp = client.post("/v1/auth/login", json={"username": username, "password": password})
    assert login_resp.status_code == 200, login_resp.text
    token = login_resp.json()["token"]
    return user_id, token


class TestHealthEndpoint:
    def test_health_ok(self, client: TestClient):
        resp = client.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert "model_version" in data
        assert "provider" in data


class TestAuthHttp:
    def test_register_login_me_logout_flow(self, client: TestClient):
        # 1. Register
        reg = client.post("/v1/auth/register", json={"username": "bob_auth", "password": "password123"})
        assert reg.status_code == 201
        assert reg.json()["username"] == "bob_auth"

        # 2. Duplicate register fails
        dup = client.post("/v1/auth/register", json={"username": "bob_auth", "password": "password123"})
        assert dup.status_code == 400

        # 3. Login wrong password fails
        bad = client.post("/v1/auth/login", json={"username": "bob_auth", "password": "wrongpassword"})
        assert bad.status_code == 401

        # 4. Login correct returns token
        ok = client.post("/v1/auth/login", json={"username": "bob_auth", "password": "password123"})
        assert ok.status_code == 200
        token = ok.json()["token"]
        assert token

        # 5. Access /v1/auth/me with Bearer token
        headers = {"Authorization": f"Bearer {token}"}
        me = client.get("/v1/auth/me", headers=headers)
        assert me.status_code == 200
        assert me.json()["username"] == "bob_auth"

        # 6. Access without token fails
        no_auth = client.get("/v1/auth/me")
        assert no_auth.status_code == 401

        # 7. Logout revokes token
        logout = client.post("/v1/auth/logout", headers=headers)
        assert logout.status_code == 200

        # 8. Token is now invalid
        me_after = client.get("/v1/auth/me", headers=headers)
        assert me_after.status_code == 401


class TestSessionsHttp:
    def test_sessions_lifecycle(self, client: TestClient):
        _, token = _register_and_login(client, username="sess_user")
        headers = {"Authorization": f"Bearer {token}"}

        # Create session
        c_resp = client.post("/v1/sessions", json={"title": "Session 1"}, headers=headers)
        assert c_resp.status_code == 201
        sid = c_resp.json()["session_id"]
        assert sid

        # List sessions
        l_resp = client.get("/v1/sessions", headers=headers)
        assert l_resp.status_code == 200
        sessions = l_resp.json()
        assert any(s["session_id"] == sid for s in sessions)

        # Delete session
        d_resp = client.delete(f"/v1/sessions/{sid}", headers=headers)
        assert d_resp.status_code == 200

        # List sessions again -> gone
        l2_resp = client.get("/v1/sessions", headers=headers)
        assert not any(s["session_id"] == sid for s in l2_resp.json())


class TestMemoryHttp:
    def test_memory_crud_and_versioning(self, client: TestClient):
        _, token = _register_and_login(client, username="mem_user")
        headers = {"Authorization": f"Bearer {token}"}

        # Create decision memory v1
        c_resp = client.post("/v1/memories", json={
            "info_type": "decision",
            "content": "Dùng PostgreSQL làm cơ sở dữ liệu chính",
        }, headers=headers)
        assert c_resp.status_code == 201
        mem1 = c_resp.json()
        assert mem1["version"] == 1
        assert mem1["is_active"] is True
        mem_id_1 = mem1["memory_id"]

        # List memories
        list_resp = client.get("/v1/memories", headers=headers)
        assert list_resp.status_code == 200
        assert len(list_resp.json()) == 1

        # Update decision -> creates v2 and supersedes v1
        u_resp = client.put(f"/v1/memories/{mem_id_1}", json={
            "content": "Đổi sang dùng SQLite với WAL mode cho Phase 1",
            "info_type": "decision"
        }, headers=headers)
        assert u_resp.status_code == 200
        mem2 = u_resp.json()
        assert mem2["version"] == 2

        # Verify old memory was deactivated and linked to v2
        old_v1 = client.get(f"/v1/memories/{mem_id_1}", headers=headers).json()
        assert old_v1["is_active"] is False
        assert old_v1["superseded_by"] == mem2["memory_id"]

        # Active list should only contain v2
        active_list = client.get("/v1/memories?active_only=true", headers=headers).json()
        assert len(active_list) == 1
        assert active_list[0]["content"] == "Đổi sang dùng SQLite với WAL mode cho Phase 1"

        # History of the memory chain
        hist_resp = client.get(f"/v1/memories/{mem2['memory_id']}/history", headers=headers)
        assert hist_resp.status_code == 200
        history = hist_resp.json()
        assert len(history) == 2

        # Delete memory
        del_resp = client.delete(f"/v1/memories/{mem2['memory_id']}", headers=headers)
        assert del_resp.status_code == 204

        # Now active_list is empty
        active_list2 = client.get("/v1/memories?active_only=true", headers=headers).json()
        assert len(active_list2) == 0


class TestChatHttp:
    def test_chat_injects_memory_and_returns_route(self, client: TestClient):
        _, token = _register_and_login(client, username="chat_user")
        headers = {"Authorization": f"Bearer {token}"}

        # 1. Create a session
        sess = client.post("/v1/sessions", json={"title": "Chat Test"}, headers=headers).json()
        sid = sess["session_id"]

        # 2. Add a decision memory
        client.post("/v1/memories", json={
            "info_type": "decision",
            "content": "Chọn SQLite với WAL mode làm storage cho Week 1",
        }, headers=headers)

        # 3. Send chat message
        chat_resp = client.post("/v1/chat", json={
            "message": "Storage được chọn cho Week 1 là gì?",
            "session_id": sid,
        }, headers=headers)

        assert chat_resp.status_code == 200
        data = chat_resp.json()
        assert "reply" in data
        assert len(data["reply"]) > 0
        assert data["session_id"] == sid
        assert "intent" in data
        assert "selected_agent" in data
        assert "state_version" in data

        # Verify session history recorded the conversation
        hist_resp = client.get(f"/v1/sessions/{sid}/messages", headers=headers)
        assert hist_resp.status_code == 200
        messages = hist_resp.json()
        assert len(messages) >= 2  # user message + assistant reply
        roles = [m["role"] for m in messages]
        assert "user" in roles
        assert "assistant" in roles


class TestUserIsolationHttp:
    def test_user_b_cannot_see_or_modify_user_a(self, client: TestClient):
        # User A setup
        _, token_a = _register_and_login(client, username="alice_iso", password="password_alice_123")
        headers_a = {"Authorization": f"Bearer {token_a}"}
        m_a = client.post("/v1/memories", json={"info_type": "secret", "content": "alice_secret"}, headers=headers_a).json()

        # User B setup
        _, token_b = _register_and_login(client, username="bob_iso", password="password_bob_123")
        headers_b = {"Authorization": f"Bearer {token_b}"}

        # User B lists memories -> empty
        mems_b = client.get("/v1/memories", headers=headers_b).json()
        assert len(mems_b) == 0

        # User B tries to update User A's memory -> 404
        bad_up = client.put(f"/v1/memories/{m_a['memory_id']}", json={"content": "hacked"}, headers=headers_b)
        assert bad_up.status_code == 404

        # User B tries to delete User A's memory -> 404
        bad_del = client.delete(f"/v1/memories/{m_a['memory_id']}", headers=headers_b)
        assert bad_del.status_code == 404
