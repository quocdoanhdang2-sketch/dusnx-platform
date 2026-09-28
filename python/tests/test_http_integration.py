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

import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from apps.ai_api.main import app
import apps.ai_api.auth as auth_mod
import apps.ai_api.memory as mem_mod

REPO_ROOT = Path(__file__).resolve().parents[2]


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
    """Verify DUSN-X state is persisted per user across turns, sessions, DB reopen, and real process restarts."""

    def _chat(self, client: TestClient, headers: dict, sid: str, msg: str) -> dict:
        r = client.post("/v1/chat", json={"message": msg, "session_id": sid}, headers=headers)
        assert r.status_code == 200, r.text
        return r.json()

    def test_state_version_increases_across_turns(self, client: TestClient):
        """Two consecutive turns in the same session: state_version must strictly increase."""
        _, token = _register_and_login(client, username="state_turns")
        h = {"Authorization": f"Bearer {token}"}
        sid = client.post("/v1/sessions", json={"title": "turns"}, headers=h).json()["session_id"]

        r1 = self._chat(client, h, sid, "Xin chào DUSN-X")
        r2 = self._chat(client, h, sid, "Tiếp tục nào")

        v1 = r1.get("state_version")
        v2 = r2.get("state_version")
        assert v1 is not None, f"Turn 1 state_version must not be None (got {r1})"
        assert v2 is not None, f"Turn 2 state_version must not be None (got {r2})"
        assert v2 > v1, f"state_version must strictly increase: {v1} -> {v2}"

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
        assert v1 is not None, f"Session 1 state_version must not be None (got {r1})"
        assert v2 is not None, f"Session 2 state_version must not be None (got {r2})"
        assert v2 > v1, f"Second session state_version {v2} should be > first session {v1}"

    def test_state_survives_db_reopen(self, client: TestClient, tmp_path, monkeypatch):
        """Simulate DB reopen: close DB connection singleton and reopen from same SQLite file."""
        import apps.ai_api.memory as mem_mod

        _, token = _register_and_login(client, username="state_db_reopen")
        h = {"Authorization": f"Bearer {token}"}
        sid = client.post("/v1/sessions", json={"title": "reopen"}, headers=h).json()["session_id"]

        r1 = self._chat(client, h, sid, "Trước khi reopen DB")
        v1 = r1.get("state_version")
        assert v1 is not None, "Turn 1 state_version must not be None"

        # Close and reset the DB singleton (simulating connection close / reopen)
        if mem_mod._memory_db is not None:
            mem_mod._memory_db.close()
            mem_mod._memory_db = None

        # Second chat — DB is re-opened from same SQLite file on disk, state must persist
        sid2 = client.post("/v1/sessions", json={"title": "after_reopen"}, headers=h).json()["session_id"]
        r2 = self._chat(client, h, sid2, "Sau khi reopen DB")
        v2 = r2.get("state_version")
        assert v2 is not None, "Turn 2 state_version must not be None"
        assert v2 > v1, f"After DB reopen, state_version {v2} should be > pre-reopen {v1}"

    def test_state_survives_real_process_restart(self, tmp_path):
        """Actually spawn independent Python processes pointing to the same DUSNX_DATA_DIR."""
        import subprocess
        import sys
        import json

        data_dir = str(tmp_path / "proc_restart_data")
        script = (
            "import os, sys, json\n"
            "from fastapi.testclient import TestClient\n"
            "sys.path.insert(0, 'python')\n"
            "from apps.ai_api.main import app\n"
            "client = TestClient(app)\n"
            "step = sys.argv[1]\n"
            "if step == 'step1':\n"
            "    reg = client.post('/v1/auth/register', json={'username': 'restart_user', 'password': 'password123'}).json()\n"
            "    login = client.post('/v1/auth/login', json={'username': 'restart_user', 'password': 'password123'}).json()\n"
            "    token = login['token']\n"
            "    h = {'Authorization': f'Bearer {token}'}\n"
            "    sid = client.post('/v1/sessions', json={'title': 's'}, headers=h).json()['session_id']\n"
            "    c = client.post('/v1/chat', json={'message': 'Lượt 1 trước restart', 'session_id': sid}, headers=h).json()\n"
            "    print(json.dumps({'state_version': c['state_version']}))\n"
            "elif step == 'step2':\n"
            "    login = client.post('/v1/auth/login', json={'username': 'restart_user', 'password': 'password123'}).json()\n"
            "    token = login['token']\n"
            "    h = {'Authorization': f'Bearer {token}'}\n"
            "    sid = client.post('/v1/sessions', json={'title': 's2'}, headers=h).json()['session_id']\n"
            "    c = client.post('/v1/chat', json={'message': 'Lượt 2 sau restart', 'session_id': sid}, headers=h).json()\n"
            "    print(json.dumps({'state_version': c['state_version']}))\n"
        )

        env = os.environ.copy()
        env["DUSNX_DATA_DIR"] = data_dir
        env["PYTHONPATH"] = "python"

        # Process 1: run step1 and exit
        p1 = subprocess.run(
            [sys.executable, "-c", script, "step1"],
            cwd=str(REPO_ROOT),
            env=env,
            capture_output=True,
            text=True,
        )
        assert p1.returncode == 0, f"Process 1 failed: {p1.stderr}"
        res1 = json.loads(p1.stdout.strip())
        v1 = res1["state_version"]
        assert v1 is not None and v1 >= 1

        # Process 2: run step2 pointing to same data_dir after Process 1 is dead
        p2 = subprocess.run(
            [sys.executable, "-c", script, "step2"],
            cwd=str(REPO_ROOT),
            env=env,
            capture_output=True,
            text=True,
        )
        assert p2.returncode == 0, f"Process 2 failed: {p2.stderr}"
        res2 = json.loads(p2.stdout.strip())
        v2 = res2["state_version"]
        assert v2 is not None
        assert v2 > v1, f"State version after true process restart must increase: {v1} -> {v2}"

    def test_state_not_shared_between_users(self, client: TestClient):
        """Two different users must have completely independent state vectors and versions."""
        u_a, token_a = _register_and_login(client, username="state_user_a", password="passA_state123")
        u_b, token_b = _register_and_login(client, username="state_user_b", password="passB_state123")
        ha = {"Authorization": f"Bearer {token_a}"}
        hb = {"Authorization": f"Bearer {token_b}"}

        sid_a = client.post("/v1/sessions", json={"title": "a"}, headers=ha).json()["session_id"]
        sid_b = client.post("/v1/sessions", json={"title": "b"}, headers=hb).json()["session_id"]

        # User A chats three times to advance state
        for i in range(3):
            self._chat(client, ha, sid_a, f"User A tin nhắn {i}")

        # User B chats once
        rb = self._chat(client, hb, sid_b, "User B lần đầu")
        vb = rb.get("state_version")
        assert vb is not None, "User B state_version must not be None"
        assert vb == 1, f"User B first turn state_version must be 1, got {vb}"

        # Verify state store records directly in DB
        db = mem_mod.get_memory_db()
        st_a = db.get_dusnx_state(u_a)
        st_b = db.get_dusnx_state(u_b)
        assert st_a is not None, "User A state must be persisted"
        assert st_b is not None, "User B state must be persisted"
        assert st_a["state_version"] == 3
        assert st_b["state_version"] == 1
        assert st_a["state_blob"] != st_b["state_blob"], "User A and User B state blobs must be distinct"


class TestDecisionModificationFlow:
    """Verify conversational decision-modification flow with hardened detect-confirm behavior."""

    def _chat(self, client: TestClient, headers: dict, sid: str, msg: str) -> dict:
        r = client.post("/v1/chat", json={"message": msg, "session_id": sid}, headers=headers)
        assert r.status_code == 200, r.text
        return r.json()

    def _setup(self, client: TestClient, username: str, decision_content: str):
        u_id, token = _register_and_login(client, username=username)
        h = {"Authorization": f"Bearer {token}"}
        sid = client.post("/v1/sessions", json={"title": "dm"}, headers=h).json()["session_id"]
        mem = client.post("/v1/memories", json={
            "info_type": "decision",
            "content": decision_content,
        }, headers=h).json()
        return u_id, h, sid, mem["memory_id"]

    def test_detect_modify_intent_and_ask_confirm(self, client: TestClient):
        """Sending a decision-modify message triggers confirmation request without altering memory."""
        _, h, sid, old_mid = self._setup(
            client, "dm_detect", "Dùng PostgreSQL làm DB chính"
        )
        r = self._chat(client, h, sid,
                       "Tôi muốn thay đổi quyết định sang dùng SQLite thay vì PostgreSQL")
        assert r["routing_source"] == "decision_flow"
        assert "decision_modify" in r["intent"] or "awaiting" in r["intent"]
        assert "Có" in r["reply"] or "Không" in r["reply"] or "xác nhận" in r["reply"].lower()
        assert r["state_version"] is not None, "state_version must be returned"

        # Old memory must remain untouched
        old_mem = client.get(f"/v1/memories/{old_mid}", headers=h).json()
        assert old_mem["is_active"] is True
        assert old_mem["superseded_by"] is None

    def test_confirm_yes_applies_supersede(self, client: TestClient):
        """Replying 'Có' confirms modification: supersedes old memory, creates 1 new active version."""
        _, h, sid, old_mid = self._setup(
            client, "dm_confirm_yes", "Dùng PostgreSQL làm DB chính"
        )
        self._chat(client, h, sid, "Thay đổi quyết định sang dùng SQLite với WAL mode")
        r = self._chat(client, h, sid, "Có")

        assert r["intent"] == "decision_update"
        assert "✅" in r["reply"]
        assert "PostgreSQL" in r["reply"]
        assert "SQLite" in r["reply"]
        assert r["state_version"] is not None

        # Verify old memory is deactivated
        old_mem = client.get(f"/v1/memories/{old_mid}", headers=h).json()
        assert old_mem["is_active"] is False
        assert old_mem["superseded_by"] is not None

        # Verify exactly one active memory exists with new content
        active = client.get("/v1/memories?active_only=true", headers=h).json()
        assert len(active) == 1
        assert "SQLite với WAL mode" in active[0]["content"]

        # History must contain exactly 2 versions
        history = client.get(f"/v1/memories/{old_mem['superseded_by']}/history", headers=h).json()
        assert len(history) == 2

    def test_confirm_dong_y_and_xac_nhan(self, client: TestClient):
        """Explicit affirmations like 'đồng ý' and 'xác nhận' must confirm the modification."""
        # 1. Test "đồng ý"
        _, h1, s1, mid1 = self._setup(client, "dm_dong_y", "Frontend dùng Vue.js")
        self._chat(client, h1, s1, "Thay đổi quyết định sang dùng React")
        r1 = self._chat(client, h1, s1, "Tôi đồng ý")
        assert r1["intent"] == "decision_update"
        assert "✅" in r1["reply"]
        m1_old = client.get(f"/v1/memories/{mid1}", headers=h1).json()
        assert m1_old["is_active"] is False

        # 2. Test "xác nhận"
        _, h2, s2, mid2 = self._setup(client, "dm_xac_nhan", "Backend dùng Express")
        self._chat(client, h2, s2, "Thay đổi quyết định sang dùng FastAPI")
        r2 = self._chat(client, h2, s2, "Xác nhận thay đổi")
        assert r2["intent"] == "decision_update"
        assert "✅" in r2["reply"]
        m2_old = client.get(f"/v1/memories/{mid2}", headers=h2).json()
        assert m2_old["is_active"] is False

    def test_reject_khong_dong_y(self, client: TestClient):
        """'không đồng ý' must REJECT the proposal and preserve the active decision."""
        _, h, sid, old_mid = self._setup(client, "dm_rej_kdy", "Dùng PostgreSQL làm DB")
        self._chat(client, h, sid, "Thay đổi quyết định sang dùng MongoDB")
        r = self._chat(client, h, sid, "Tôi không đồng ý")

        assert r["intent"] == "decision_update_cancelled"
        assert "huỷ" in r["reply"].lower() or "hủy" in r["reply"].lower() or "giữ nguyên" in r["reply"].lower()
        assert r["state_version"] is not None

        old_mem = client.get(f"/v1/memories/{old_mid}", headers=h).json()
        assert old_mem["is_active"] is True
        assert old_mem["superseded_by"] is None

    def test_reject_khong_xac_nhan(self, client: TestClient):
        """'không xác nhận' must REJECT the proposal and preserve the active decision."""
        _, h, sid, old_mid = self._setup(client, "dm_rej_kxn", "Dùng PostgreSQL làm DB")
        self._chat(client, h, sid, "Thay đổi quyết định sang dùng Cassandra")
        r = self._chat(client, h, sid, "Không xác nhận nhé")

        assert r["intent"] == "decision_update_cancelled"
        old_mem = client.get(f"/v1/memories/{old_mid}", headers=h).json()
        assert old_mem["is_active"] is True

    def test_reject_khong_dung(self, client: TestClient):
        """'không đúng' must REJECT the proposal and preserve the active decision."""
        _, h, sid, old_mid = self._setup(client, "dm_rej_kd", "Dùng PostgreSQL làm DB")
        self._chat(client, h, sid, "Thay đổi quyết định sang dùng SQLite")
        r = self._chat(client, h, sid, "Không đúng, huỷ đi")

        assert r["intent"] == "decision_update_cancelled"
        old_mem = client.get(f"/v1/memories/{old_mid}", headers=h).json()
        assert old_mem["is_active"] is True

    def test_reject_dung_thay(self, client: TestClient):
        """'đừng thay' must REJECT the proposal and preserve the active decision."""
        _, h, sid, old_mid = self._setup(client, "dm_rej_dt", "Dùng PostgreSQL làm DB")
        self._chat(client, h, sid, "Thay đổi quyết định sang dùng MariaDB")
        r = self._chat(client, h, sid, "Thôi đừng thay")

        assert r["intent"] == "decision_update_cancelled"
        old_mem = client.get(f"/v1/memories/{old_mid}", headers=h).json()
        assert old_mem["is_active"] is True

    def test_reject_khong_giu_nguyen(self, client: TestClient):
        """'không, giữ nguyên' must REJECT the proposal and preserve the active decision."""
        _, h, sid, old_mid = self._setup(client, "dm_rej_kgn", "Dùng PostgreSQL làm DB")
        self._chat(client, h, sid, "Thay đổi quyết định sang dùng DynamoDB")
        r = self._chat(client, h, sid, "Không, giữ nguyên quyết định cũ")

        assert r["intent"] == "decision_update_cancelled"
        old_mem = client.get(f"/v1/memories/{old_mid}", headers=h).json()
        assert old_mem["is_active"] is True

    def test_reject_cancel_and_no(self, client: TestClient):
        """'cancel' and 'no' must REJECT the proposal."""
        _, h, sid, old_mid = self._setup(client, "dm_rej_en", "Dùng PostgreSQL làm DB")
        self._chat(client, h, sid, "Thay đổi quyết định sang dùng Redis")
        r = self._chat(client, h, sid, "Cancel")
        assert r["intent"] == "decision_update_cancelled"
        old_mem = client.get(f"/v1/memories/{old_mid}", headers=h).json()
        assert old_mem["is_active"] is True

    def test_ambiguous_and_contradictory_replies_re_ask(self, client: TestClient):
        """Ambiguous or contradictory replies must re-ask without altering memory."""
        _, h, sid, old_mid = self._setup(client, "dm_ambig_all", "Dùng PostgreSQL làm DB")
        self._chat(client, h, sid, "Thay đổi quyết định sang dùng Neo4j")

        # Case 1: Uncertainty
        r1 = self._chat(client, h, sid, "Hmm, tôi không chắc lắm")
        assert r1["intent"] == "awaiting_confirm"
        assert "Có" in r1["reply"] and "Không" in r1["reply"]

        # Case 2: Contradictory signals ('có' + 'đừng thay')
        r2 = self._chat(client, h, sid, "Có nhưng mà thôi đừng thay")
        assert r2["intent"] == "awaiting_confirm"

        # Case 3: Contradictory signals ('đồng ý' + 'thôi')
        r3 = self._chat(client, h, sid, "Đồng ý nhưng mà thôi suy nghĩ lại")
        assert r3["intent"] == "awaiting_confirm"

        # Memory must still be active and unchanged
        old_mem = client.get(f"/v1/memories/{old_mid}", headers=h).json()
        assert old_mem["is_active"] is True
        assert old_mem["superseded_by"] is None

    def test_double_resolve_rejected_atomically(self, client: TestClient):
        """Resolving a pending decision twice via API returns 404 on the second attempt."""
        _, h, sid, old_mid = self._setup(client, "dm_double_res", "Dùng PostgreSQL")
        self._chat(client, h, sid, "Thay đổi quyết định sang dùng SQLite")

        # Get pending ID
        pendings = client.get("/v1/pending-decisions", headers=h).json()
        assert len(pendings) == 1
        pid = pendings[0]["pending_id"]

        # First resolve: accepts
        r1 = client.post(f"/v1/pending-decisions/{pid}/resolve", json={"accepted": True}, headers=h)
        assert r1.status_code == 200
        assert r1.json()["resolved"]["status"] == "confirmed"

        # Second resolve: must fail with 404 (already resolved)
        r2 = client.post(f"/v1/pending-decisions/{pid}/resolve", json={"accepted": True}, headers=h)
        assert r2.status_code == 404

        # Verify only 1 new active memory version exists
        active = client.get("/v1/memories?active_only=true", headers=h).json()
        assert len(active) == 1
        assert "SQLite" in active[0]["content"]

    def test_stale_pending_decision_when_old_memory_deleted_or_superseded(self, client: TestClient):
        """If the old memory was deleted/superseded before confirmation, resolve fails with 409."""
        _, h, sid, old_mid = self._setup(client, "dm_stale", "Dùng PostgreSQL")
        self._chat(client, h, sid, "Thay đổi quyết định sang dùng SQLite")

        # Fetch pending ID
        pendings = client.get("/v1/pending-decisions", headers=h).json()
        assert len(pendings) == 1
        pid = pendings[0]["pending_id"]

        # Now simulate old memory being deleted before the user confirms
        del_resp = client.delete(f"/v1/memories/{old_mid}", headers=h)
        assert del_resp.status_code == 204

        # Now try to resolve the pending decision
        res = client.post(f"/v1/pending-decisions/{pid}/resolve", json={"accepted": True}, headers=h)
        assert res.status_code == 409
        assert "không còn hiệu lực" in res.json()["detail"]

        # No new active memory was created
        active = client.get("/v1/memories?active_only=true", headers=h).json()
        assert len(active) == 0

    def test_simulated_db_error_triggers_atomic_rollback(self, client: TestClient):
        """Simulate an error during the atomic supersede: transaction rolls back, status is not confirmed."""
        import sqlite3
        _, h, sid, old_mid = self._setup(client, "dm_rollback", "Dùng PostgreSQL")
        self._chat(client, h, sid, "Thay đổi quyết định sang dùng SQLite")

        pendings = client.get("/v1/pending-decisions", headers=h).json()
        pid = pendings[0]["pending_id"]

        db = mem_mod.get_memory_db()

        # Create a trigger that raises an error when updating memories (simulating write/constraint failure)
        db._conn.execute(
            "CREATE TRIGGER fail_mem_update BEFORE UPDATE ON memories BEGIN SELECT RAISE(ABORT, 'Simulated DB failure during supersede'); END;"
        )

        with pytest.raises(sqlite3.Error):
            db.resolve_pending_decision_atomic(
                user_id=pendings[0]["user_id"],
                pending_id=pid,
                accepted=True,
            )

        # Drop the trigger
        db._conn.execute("DROP TRIGGER fail_mem_update")

        # Status must NOT be confirmed! It must be rolled back to awaiting_confirm
        p_check = db.get_pending_decision(pendings[0]["user_id"], pid)
        assert p_check["status"] == "awaiting_confirm", "Pending record must not remain confirmed after rollback"

        # Old memory must still be active
        old_mem = client.get(f"/v1/memories/{old_mid}", headers=h).json()
        assert old_mem["is_active"] is True
        assert old_mem["superseded_by"] is None

    def test_user_b_cannot_view_or_resolve_user_a_pending(self, client: TestClient):
        """User B cannot view or resolve User A's pending decision via API or chat."""
        # User A creates pending decision
        u_a, ha, sid_a, old_mid_a = self._setup(client, "alice_pending", "Alice quyết định A")
        self._chat(client, ha, sid_a, "Thay đổi quyết định sang quyết định A mới")
        p_a = client.get("/v1/pending-decisions", headers=ha).json()
        assert len(p_a) == 1
        pid_a = p_a[0]["pending_id"]

        # User B registers and logs in
        u_b, token_b = _register_and_login(client, username="bob_attacker")
        hb = {"Authorization": f"Bearer {token_b}"}
        sid_b = client.post("/v1/sessions", json={"title": "bob_s"}, headers=hb).json()["session_id"]

        # 1. User B lists pending decisions -> empty
        p_b = client.get("/v1/pending-decisions", headers=hb).json()
        assert len(p_b) == 0

        # 2. User B tries to resolve User A's pending decision via API -> 404
        bad_res = client.post(f"/v1/pending-decisions/{pid_a}/resolve", json={"accepted": True}, headers=hb)
        assert bad_res.status_code == 404

        # 3. User B chats "Có" in User B's session -> should NOT resolve User A's pending
        rb = self._chat(client, hb, sid_b, "Có")
        # User A's pending decision must STILL be awaiting_confirm
        p_a_after = client.get("/v1/pending-decisions", headers=ha).json()
        assert len(p_a_after) == 1
        assert p_a_after[0]["status"] == "awaiting_confirm"

        # Alice's old memory is still active
        mem_a = client.get(f"/v1/memories/{old_mid_a}", headers=ha).json()
        assert mem_a["is_active"] is True

    def test_no_matching_decision_asks_clarify(self, client: TestClient):
        """If no active decision matches, the bot asks for clarification instead of hallucinating."""
        _, token = _register_and_login(client, username="dm_no_match")
        h = {"Authorization": f"Bearer {token}"}
        sid = client.post("/v1/sessions", json={"title": "nm"}, headers=h).json()["session_id"]
        r = self._chat(client, h, sid, "Tôi muốn thay đổi quyết định sang dùng Redis")
        assert r["routing_source"] == "decision_flow"
        assert r["next_action"] == "clarify"

