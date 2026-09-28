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


class TestChatStatePersistence:
    """Verify DUSN-X state is persisted per user across turns, sessions, and after DB reset (restart simulation)."""

    def _chat(self, client: TestClient, headers: dict, sid: str, msg: str) -> dict:
        r = client.post("/v1/chat", json={"message": msg, "session_id": sid}, headers=headers)
        assert r.status_code == 200, r.text
        return r.json()

    def test_state_version_increases_across_turns(self, client: TestClient):
        """Two consecutive turns in the same session: state_version must increase."""
        _, token = _register_and_login(client, username="state_turns")
        h = {"Authorization": f"Bearer {token}"}
        sid = client.post("/v1/sessions", json={"title": "turns"}, headers=h).json()["session_id"]

        r1 = self._chat(client, h, sid, "Xin chào DUSN-X")
        r2 = self._chat(client, h, sid, "Tiếp tục nào")

        v1 = r1.get("state_version")
        v2 = r2.get("state_version")
        # In bootstrap mode version increments; in trained mode also increments
        if v1 is not None and v2 is not None:
            assert v2 > v1, f"state_version must increase: {v1} -> {v2}"

    def test_state_persists_across_sessions(self, client: TestClient):
        """Same user, two separate sessions: state_version in session2 should be > session1 turn1."""
        _, token = _register_and_login(client, username="state_sessions")
        h = {"Authorization": f"Bearer {token}"}

        sid1 = client.post("/v1/sessions", json={"title": "s1"}, headers=h).json()["session_id"]
        sid2 = client.post("/v1/sessions", json={"title": "s2"}, headers=h).json()["session_id"]

        r1 = self._chat(client, h, sid1, "Phiên một")
        r2 = self._chat(client, h, sid2, "Phiên hai")

        v1 = r1.get("state_version")
        v2 = r2.get("state_version")
        if v1 is not None and v2 is not None:
            assert v2 > v1, f"Second session state_version {v2} should be > first session {v1}"

    def test_state_survives_restart(self, client: TestClient, tmp_path, monkeypatch):
        """Simulate restart: close DB singleton and reopen from same tmp_path — state_version continues."""
        import apps.ai_api.memory as mem_mod

        _, token = _register_and_login(client, username="state_restart")
        h = {"Authorization": f"Bearer {token}"}
        sid = client.post("/v1/sessions", json={"title": "restart"}, headers=h).json()["session_id"]

        r1 = self._chat(client, h, sid, "Trước khi restart")
        v1 = r1.get("state_version")

        # Simulate restart: close and reset the singleton
        if mem_mod._memory_db is not None:
            mem_mod._memory_db.close()
            mem_mod._memory_db = None

        # Second chat — DB is re-opened from same tmp_path, state should persist
        sid2 = client.post("/v1/sessions", json={"title": "after"}, headers=h).json()["session_id"]
        r2 = self._chat(client, h, sid2, "Sau khi restart")
        v2 = r2.get("state_version")

        if v1 is not None and v2 is not None:
            assert v2 > v1, f"After restart, state_version {v2} should be > pre-restart {v1}"

    def test_state_not_shared_between_users(self, client: TestClient):
        """Two different users must have independent state_versions."""
        _, token_a = _register_and_login(client, username="state_user_a", password="passA_state123")
        _, token_b = _register_and_login(client, username="state_user_b", password="passB_state123")
        ha = {"Authorization": f"Bearer {token_a}"}
        hb = {"Authorization": f"Bearer {token_b}"}

        sid_a = client.post("/v1/sessions", json={"title": "a"}, headers=ha).json()["session_id"]
        sid_b = client.post("/v1/sessions", json={"title": "b"}, headers=hb).json()["session_id"]

        # User A chats three times to build state
        for i in range(3):
            self._chat(client, ha, sid_a, f"User A tin nhắn {i}")

        # User B chats once
        rb = self._chat(client, hb, sid_b, "User B lần đầu")
        vb = rb.get("state_version")

        # User B's state_version should be low (not contaminated by User A's)
        if vb is not None:
            assert vb <= 2, f"User B state_version {vb} should not be contaminated by User A"


class TestDecisionModificationFlow:
    """Verify the conversational decision-modification flow (detect -> confirm -> apply/reject)."""

    def _chat(self, client: TestClient, headers: dict, sid: str, msg: str) -> dict:
        r = client.post("/v1/chat", json={"message": msg, "session_id": sid}, headers=headers)
        assert r.status_code == 200, r.text
        return r.json()

    def _setup(self, client: TestClient, username: str, decision_content: str):
        _, token = _register_and_login(client, username=username)
        h = {"Authorization": f"Bearer {token}"}
        sid = client.post("/v1/sessions", json={"title": "dm"}, headers=h).json()["session_id"]
        mem = client.post("/v1/memories", json={
            "info_type": "decision",
            "content": decision_content,
        }, headers=h).json()
        return h, sid, mem["memory_id"]

    def test_detect_modify_intent_and_ask_confirm(self, client: TestClient):
        """Sending a decision-modify message triggers a confirmation request."""
        h, sid, _ = self._setup(
            client, "dm_detect", "Dùng PostgreSQL làm DB chính"
        )
        r = self._chat(client, h, sid,
                       "Tôi muốn thay đổi quyết định sang dùng SQLite thay vì PostgreSQL")
        assert r["routing_source"] == "decision_flow"
        assert "decision_modify" in r["intent"] or "awaiting" in r["intent"]
        assert "Có" in r["reply"] or "Không" in r["reply"] or "xác nhận" in r["reply"].lower()

    def test_confirm_yes_applies_supersede(self, client: TestClient):
        """After detection, replying 'Có' must apply the supersede and deactivate old memory."""
        h, sid, old_mid = self._setup(
            client, "dm_confirm", "Dùng PostgreSQL làm DB chính"
        )
        # Trigger detection
        self._chat(client, h, sid,
                   "Thay đổi quyết định sang dùng SQLite với WAL mode")
        # Confirm
        r = self._chat(client, h, sid, "Có")
        assert r["intent"] == "decision_update"
        assert "✅" in r["reply"] or "cập nhật" in r["reply"].lower()

        # Old memory should be deactivated
        old_mem = client.get(f"/v1/memories/{old_mid}", headers=h).json()
        assert old_mem["is_active"] is False
        assert old_mem["superseded_by"] is not None

        # Active memories should contain the new decision
        active = client.get("/v1/memories?active_only=true", headers=h).json()
        contents = [m["content"] for m in active]
        assert any("SQLite" in c for c in contents)

    def test_confirm_no_cancels_and_keeps_old(self, client: TestClient):
        """Replying 'Không' cancels the pending decision and keeps old memory active."""
        h, sid, old_mid = self._setup(
            client, "dm_cancel", "Dùng PostgreSQL làm DB chính"
        )
        self._chat(client, h, sid,
                   "Thay đổi quyết định sang dùng MySQL")
        r = self._chat(client, h, sid, "Không")
        assert "cancel" in r["intent"] or "huỷ" in r["reply"].lower() or "hủy" in r["reply"].lower()

        # Old memory must still be active
        old_mem = client.get(f"/v1/memories/{old_mid}", headers=h).json()
        assert old_mem["is_active"] is True
        assert old_mem["superseded_by"] is None

    def test_ambiguous_reply_re_asks(self, client: TestClient):
        """An ambiguous reply after detection re-asks for confirmation without applying changes."""
        h, sid, old_mid = self._setup(
            client, "dm_ambig", "Dùng PostgreSQL làm DB chính"
        )
        self._chat(client, h, sid,
                   "Thay đổi quyết định sang dùng MongoDB")
        r = self._chat(client, h, sid, "Hmm, không chắc lắm")
        # Should re-ask (awaiting_confirm or clarify)
        assert r["intent"] in ("awaiting_confirm", "decision_modify_intent")
        # Old memory must STILL be active
        old_mem = client.get(f"/v1/memories/{old_mid}", headers=h).json()
        assert old_mem["is_active"] is True

    def test_no_matching_decision_asks_clarify(self, client: TestClient):
        """If no active decision matches, the bot asks for clarification instead of hallucinating."""
        _, token = _register_and_login(client, username="dm_no_match")
        h = {"Authorization": f"Bearer {token}"}
        sid = client.post("/v1/sessions", json={"title": "nm"}, headers=h).json()["session_id"]
        # No decision memories at all
        r = self._chat(client, h, sid,
                       "Tôi muốn thay đổi quyết định sang dùng Redis")
        assert r["routing_source"] == "decision_flow"
        assert r["next_action"] == "clarify"

