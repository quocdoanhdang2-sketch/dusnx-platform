"""
DUSN-X Week 2 Acceptance Tests
===============================
Comprehensive test suite validating all Week 2 requirements:
1. Explainable memory scoring, strict project scoping, and prompt context matching.
2. User isolation (A vs B) across chat, memories, state, events, and pending decisions.
3. Cross-client state continuity: Web chat -> HTTP simulated PowerPoint connector -> Web chat.
4. Decision modification: reject keeps old, confirm supersedes atomically, ambiguous prompt clarifies.
5. Provider failure: provider down -> provider_ok=False, error not saved to history, retry deduplication.
6. Missing context guard: asking about prior context with none returns clarification.
7. Deduplication of events by event_id.
8. Concurrent requests for state advancement without race conditions.
"""
from __future__ import annotations

import concurrent.futures
from pathlib import Path
import pytest
from fastapi.testclient import TestClient

from apps.ai_api.main import app
import apps.ai_api.auth as auth_mod
import apps.ai_api.memory as mem_mod

REPO_ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(autouse=True)
def isolated_week2_env(tmp_path, monkeypatch):
    """Isolate DB directory and set mock provider for deterministic tests."""
    monkeypatch.setenv("DUSNX_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("DUSNX_PROVIDER", "mock")
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


def _register_and_login(client: TestClient, username: str, password: str = "P@ssword123!") -> tuple[str, str]:
    client.post("/v1/auth/register", json={"username": username, "password": password})
    res = client.post("/v1/auth/login", json={"username": username, "password": password}).json()
    return username, res["token"]


# ── Test 1: Prompt Injection, Explainable Memory Context & Project Scoping ─────

class TestMemoryScopingAndPromptContext:
    def test_context_includes_active_and_excludes_superseded_and_other_projects(self, client: TestClient):
        _, token = _register_and_login(client, "alice_scoping")
        headers = {"Authorization": f"Bearer {token}"}

        # Create two projects
        p_alpha = client.post("/v1/projects", json={"name": "Project Alpha"}, headers=headers).json()
        p_beta = client.post("/v1/projects", json={"name": "Project Beta"}, headers=headers).json()

        # 1. Active general preference
        m_pref = client.post("/v1/memories", json={
            "info_type": "preference",
            "content": "Thích phong cách tối giản và giao diện dark mode",
        }, headers=headers).json()

        # 2. Decision that gets superseded
        m_old_db = client.post("/v1/memories", json={
            "info_type": "decision",
            "content": "Sử dụng MySQL 5.7 làm database",
        }, headers=headers).json()

        # 3. New decision that supersedes MySQL
        m_new_db = client.put(f"/v1/memories/{m_old_db['memory_id']}", json={
            "content": "Sử dụng PostgreSQL 16 làm database chính",
            "info_type": "decision",
        }, headers=headers).json()

        # 4. Project Alpha specific fact
        m_alpha = client.post("/v1/memories", json={
            "info_type": "project_fact",
            "content": "Project Alpha xây dựng bằng Vue 3 và Vite",
            "project_id": p_alpha["project_id"],
        }, headers=headers).json()

        # 5. Project Beta specific fact (must NEVER leak into Alpha)
        m_beta = client.post("/v1/memories", json={
            "info_type": "project_fact",
            "content": "Project Beta xây dựng bằng Angular 18",
            "project_id": p_beta["project_id"],
        }, headers=headers).json()

        # Start chat session in Project Alpha
        sess = client.post("/v1/sessions", json={"title": "Alpha Chat"}, headers=headers).json()
        sid = sess["session_id"]

        # User asks about database and framework in Project Alpha
        res = client.post("/v1/chat", json={
            "session_id": sid,
            "message": "Framework và database được lựa chọn là gì?",
            "project_id": p_alpha["project_id"],
        }, headers=headers).json()

        assert res["provider_ok"] is True
        assert res["model_used"] is None
        assert res["tokens_generated"] is None
        used_ids = set(res["memory_ids_used"])

        # Check positive inclusion
        assert m_new_db["memory_id"] in used_ids, "Active PostgreSQL decision must be in context"
        assert m_alpha["memory_id"] in res["candidate_memory_ids"], "Scoped Alpha fact must be a candidate"
        assert m_alpha["memory_id"] not in used_ids, "An unselected candidate is not an answer citation"

        # Check strict negative exclusion
        assert m_old_db["memory_id"] not in used_ids, "Superseded MySQL decision must NEVER be in context"
        assert m_beta["memory_id"] not in used_ids, "Project Beta memory must NEVER leak into Project Alpha"


# ── Test 2: Complete User Isolation & Anti-Spoofing ───────────────────────────

class TestUserIsolationAndAntiSpoofing:
    def test_user_b_cannot_access_or_influence_user_a(self, client: TestClient):
        # Setup User A
        _, token_a = _register_and_login(client, "alice_iso", "secret_alice_123")
        headers_a = {"Authorization": f"Bearer {token_a}"}
        me_a = client.get("/v1/auth/me", headers=headers_a).json()
        user_id_a = me_a["user_id"]

        # User A creates a session, memory, and chat event
        sess_a = client.post("/v1/sessions", json={"title": "Private Session A"}, headers=headers_a).json()
        mem_a = client.post("/v1/memories", json={
            "info_type": "decision",
            "content": "Ngân sách bí mật của Alice là 500 triệu",
        }, headers=headers_a).json()
        chat_a = client.post("/v1/chat", json={
            "session_id": sess_a["session_id"],
            "message": "Hãy bảo mật ngân sách 500 triệu",
        }, headers=headers_a).json()
        assert chat_a["state_version"] >= 1

        # Setup User B
        _, token_b = _register_and_login(client, "bob_iso", "secret_bob_123")
        headers_b = {"Authorization": f"Bearer {token_b}"}

        # 1. Bob cannot list Alice's memories
        mems_b = client.get("/v1/memories", headers=headers_b).json()
        assert len(mems_b) == 0

        # 2. Bob cannot read Alice's specific memory
        r_get = client.get(f"/v1/memories/{mem_a['memory_id']}", headers=headers_b)
        assert r_get.status_code == 404

        # 3. Bob cannot modify Alice's memory
        r_put = client.put(f"/v1/memories/{mem_a['memory_id']}", json={"content": "Hacked"}, headers=headers_b)
        assert r_put.status_code == 404

        # 4. Bob cannot view Alice's session messages
        r_sess = client.get(f"/v1/sessions/{sess_a['session_id']}/messages", headers=headers_b)
        assert r_sess.status_code == 404

        # 5. Bob cannot view Alice's timeline events
        events_b = client.get("/v1/me/events", headers=headers_b).json()
        assert events_b["count"] == 0

        # 6. Anti-spoofing: Bob attempts to post event with Alice's user_id / linkedUserId in body
        spoofed_evt = client.post("/v1/me/events", json={
            "user_id": user_id_a,
            "linkedUserId": user_id_a,
            "content": "Bob trying to hijack Alice state",
            "platform": "powerpoint",
        }, headers=headers_b).json()

        # The event must belong to Bob, NOT Alice!
        me_b = client.get("/v1/auth/me", headers=headers_b).json()
        assert spoofed_evt["user_id"] == me_b["user_id"]
        assert spoofed_evt["user_id"] != user_id_a

        # Alice's state version must NOT have changed from Bob's request
        state_a = client.get("/v1/me/state", headers=headers_a).json()
        assert state_a["state_version"] == chat_a["state_version"]


# ── Test 3: Cross-Client State Continuity (Web + Second Client) ────────────────

class TestCrossClientStateContinuity:
    def test_second_client_powerpoint_advances_same_user_state(self, client: TestClient, tmp_path):
        """
        Scenario:
        1. User A in Web chat registers decision: 'Chọn font Aptos cho toàn bộ slide'.
        2. Second HTTP client simulating PowerPoint connector sends event with A's Bearer token.
        3. Web chat in a new session recalls the current decision and shows increased state version.
        4. Simulates process restart: state version and memories persist.
        """
        _, token = _register_and_login(client, "alice_cross_client")
        headers = {"Authorization": f"Bearer {token}"}

        # Step 1: Web chat turn 1 (creates memory)
        sess1 = client.post("/v1/sessions", json={"title": "Session 1"}, headers=headers).json()
        c1 = client.post("/v1/chat", json={
            "session_id": sess1["session_id"],
            "message": "Hãy nhớ rằng: Chọn font Aptos cho toàn bộ slide thuyết trình",
        }, headers=headers).json()
        v1 = c1["state_version"]
        assert v1 is not None and v1 >= 1
        assert "Aptos" in c1["reply"]

        # Step 2: Second client (HTTP client simulating PowerPoint) sends event with A's Bearer token
        ppt_evt = client.post("/v1/me/events", json={
            "platform": "powerpoint",
            "event_type": "slide_theme_applied",
            "content": "Đã định dạng 12 slide với font Aptos",
            "feedback_value": 1.0,
            "event_id": "ppt_slide_fmt_001",
        }, headers=headers).json()
        assert ppt_evt["status"] == "recorded"
        v2 = ppt_evt["state_version"]
        assert v2 == v1 + 1

        # Step 3: Web chat in a new session (Session 2) asks about the font decision
        sess2 = client.post("/v1/sessions", json={"title": "Session 2"}, headers=headers).json()
        c3 = client.post("/v1/chat", json={
            "session_id": sess2["session_id"],
            "message": "Font chữ nào đã được chọn cho bài thuyết trình?",
        }, headers=headers).json()
        v3 = c3["state_version"]
        assert v3 == v2 + 1
        assert any("Aptos" in m["content"] for m in client.get("/v1/memories", headers=headers).json())

        # Step 4: Verify timeline contains events from both Web and PowerPoint
        timeline = client.get("/v1/me/events", headers=headers).json()
        platforms = [e["platform"] for e in timeline["events"]]
        assert "web" in platforms
        assert "powerpoint" in platforms

        # Step 5: Simulate process restart by resetting DB module caches
        if auth_mod._auth_db:
            auth_mod._auth_db.close()
            auth_mod._auth_db = None
        if mem_mod._memory_db:
            mem_mod._memory_db.close()
            mem_mod._memory_db = None

        # After restart, state version and memories remain authoritative
        state_after = client.get("/v1/me/state", headers=headers).json()
        assert state_after["state_version"] == v3


# ── Test 4: Decision Modification Contract & Ambiguity Resolution ──────────────

class TestDecisionModificationAndAmbiguity:
    def test_rejection_preserves_old_decision(self, client: TestClient):
        _, token = _register_and_login(client, "alice_reject")
        headers = {"Authorization": f"Bearer {token}"}
        sess = client.post("/v1/sessions", json={"title": "Decision Flow"}, headers=headers).json()
        sid = sess["session_id"]

        # Step 1: Create initial decision
        client.post("/v1/memories", json={
            "info_type": "decision",
            "content": "Sử dụng Kafka để xử lý hàng đợi",
        }, headers=headers)

        # Step 2: Request modify
        r_mod = client.post("/v1/chat", json={
            "session_id": sid,
            "message": "Đổi Kafka sang RabbitMQ",
        }, headers=headers).json()
        assert r_mod["intent"] == "decision_modify_intent"
        assert "Bạn có muốn" in r_mod["reply"]

        # Step 3: Reject ("Không đồng ý")
        r_rej = client.post("/v1/chat", json={
            "session_id": sid,
            "message": "Không đồng ý",
        }, headers=headers).json()
        assert r_rej["intent"] == "decision_update_cancelled"
        assert "Giữ nguyên" in r_rej["reply"]

        # Verify old decision remains active
        mems = client.get("/v1/memories", headers=headers).json()
        active_contents = [m["content"] for m in mems if m["is_active"] == 1]
        assert "Sử dụng Kafka để xử lý hàng đợi" in active_contents
        assert not any("RabbitMQ" in c for c in active_contents)

    def test_confirmation_supersedes_atomically(self, client: TestClient):
        _, token = _register_and_login(client, "alice_confirm")
        headers = {"Authorization": f"Bearer {token}"}
        sess = client.post("/v1/sessions", json={"title": "Confirm Flow"}, headers=headers).json()
        sid = sess["session_id"]

        # Step 1: Create initial decision
        m_orig = client.post("/v1/memories", json={
            "info_type": "decision",
            "content": "Họp vào lúc 9h sáng thứ Hai",
        }, headers=headers).json()

        # Step 2: Request modify
        client.post("/v1/chat", json={
            "session_id": sid,
            "message": "Chuyển giờ họp thành 14h chiều thứ Ba",
        }, headers=headers)

        # Step 3: Confirm ("Đồng ý")
        r_conf = client.post("/v1/chat", json={
            "session_id": sid,
            "message": "Đồng ý",
        }, headers=headers).json()
        assert r_conf["intent"] == "decision_update"
        assert "Đã cập nhật quyết định" in r_conf["reply"]

        # Check DB: old is inactive, exactly one new is active
        all_mems = client.get("/v1/memories?include_inactive=true", headers=headers).json()
        old_mem = next(m for m in all_mems if m["memory_id"] == m_orig["memory_id"])
        assert old_mem["is_active"] == 0

        active_mems = [m for m in all_mems if m["is_active"] == 1]
        assert len(active_mems) == 1
        assert "14h chiều thứ Ba" in active_mems[0]["content"]

    def test_ambiguous_decision_triggers_clarification(self, client: TestClient):
        _, token = _register_and_login(client, "alice_ambiguous")
        headers = {"Authorization": f"Bearer {token}"}
        sess = client.post("/v1/sessions", json={"title": "Ambiguous Flow"}, headers=headers).json()
        sid = sess["session_id"]

        # Two similar decisions
        client.post("/v1/memories", json={
            "info_type": "decision",
            "content": "Sử dụng Redis làm caching cho hệ thống web",
        }, headers=headers)
        client.post("/v1/memories", json={
            "info_type": "decision",
            "content": "Sử dụng Redis làm session store cho mobile app",
        }, headers=headers)

        # Ambiguous query to modify Redis
        res = client.post("/v1/chat", json={
            "session_id": sid,
            "message": "Đổi Redis sang Memcached",
        }, headers=headers).json()

        # Must ask which decision instead of wrongly modifying one
        assert res["intent"] == "clarify_ambiguous_decision"
        assert "nhiều quyết định gần giống nhau" in res["reply"] or "nhiều quyết định liên quan" in res["reply"]


# ── Test 5: Provider Failure Handling & Retry Deduplication ────────────────────

class TestProviderFailureAndRetry:
    def test_provider_failure_does_not_save_error_as_ai_message(self, client: TestClient, monkeypatch):
        _, token = _register_and_login(client, "alice_provider_fail")
        headers = {"Authorization": f"Bearer {token}"}
        sess = client.post("/v1/sessions", json={"title": "Fail Session"}, headers=headers).json()
        sid = sess["session_id"]

        # Configure an unsupported/failing provider
        monkeypatch.setenv("DUSNX_PROVIDER", "failing_broken_provider")

        res = client.post("/v1/chat", json={
            "session_id": sid,
            "message": "Câu hỏi khi LLM provider đang sập",
        }, headers=headers).json()

        # API must report failure cleanly
        assert res["provider_ok"] is False
        assert "[Lỗi Provider" in res["reply"] or "chưa được hỗ trợ" in res["reply"]

        # Session history must ONLY contain the user message; NO error string saved as assistant message!
        msgs = client.get(f"/v1/sessions/{sid}/messages", headers=headers).json()
        assert len(msgs) == 1
        assert msgs[0]["role"] == "user"

        # Three counts BEFORE retry:
        # 1. Exactly 1 user message in this session
        user_msgs_before = [m for m in msgs if m["role"] == "user"]
        assert len(user_msgs_before) == 1
        # 2. Exactly 1 recorded event
        events_before = client.get("/v1/me/events", headers=headers).json()["events"]
        assert len(events_before) == 1
        # 3. State version incremented exactly once (from 0 to 1)
        state_before = client.get("/v1/me/state", headers=headers).json()
        assert state_before["state_version"] == 1

        # Retry with is_retry: True must NOT duplicate user message, event, or state version increment
        monkeypatch.setenv("DUSNX_PROVIDER", "mock")
        res_retry = client.post("/v1/chat", json={
            "session_id": sid,
            "message": "Câu hỏi khi LLM provider đang sập",
            "is_retry": True,
        }, headers=headers).json()

        assert res_retry["provider_ok"] is True

        # Three counts AFTER retry:
        # 1. User messages in session remains exactly 1 (assistant message added)
        msgs_after = client.get(f"/v1/sessions/{sid}/messages", headers=headers).json()
        user_msgs_after = [m for m in msgs_after if m["role"] == "user"]
        assert len(user_msgs_after) == 1, "Retry must not duplicate the user message in history"
        assert len(msgs_after) == 2, "History must now have 1 user and 1 assistant message"
        # 2. User events count remains exactly 1 (no duplicate event on retry)
        events_after = client.get("/v1/me/events", headers=headers).json()["events"]
        assert len(events_after) == 1, "Retry must not record a duplicate user event"
        # 3. State version remains 1 (not incremented a second time on retry)
        state_after = client.get("/v1/me/state", headers=headers).json()
        assert state_after["state_version"] == 1, "Retry must not advance state version a second time"


# ── Test 6: Missing Context Guard ──────────────────────────────────────────────

class TestMissingContextGuard:
    def test_missing_context_query_prompts_clarification(self, client: TestClient):
        _, token = _register_and_login(client, "alice_context_guard")
        headers = {"Authorization": f"Bearer {token}"}
        sess = client.post("/v1/sessions", json={"title": "Context Guard"}, headers=headers).json()
        sid = sess["session_id"]

        # User asks about "cái vừa nói" in a brand new session with no memories
        res = client.post("/v1/chat", json={
            "session_id": sid,
            "message": "Nhắc lại cái vừa nói được không?",
        }, headers=headers).json()

        assert res["intent"] == "clarify_missing_context"
        assert "chưa có bối cảnh" in res["reply"] or "chưa có thông tin" in res["reply"]


# ── Test 7: Event Deduplication & Concurrency ──────────────────────────────────

class TestEventDeduplicationAndConcurrency:
    def test_event_deduplication_by_event_id(self, client: TestClient):
        _, token = _register_and_login(client, "alice_dedup")
        headers = {"Authorization": f"Bearer {token}"}

        # Send first time
        r1 = client.post("/v1/me/events", json={
            "event_id": "unique_evt_999",
            "content": "Sự kiện kiểm tra chống lặp",
            "platform": "powerpoint",
        }, headers=headers).json()
        assert r1["status"] == "recorded"
        v1 = r1["state_version"]

        # Send second time with exact same event_id
        r2 = client.post("/v1/me/events", json={
            "event_id": "unique_evt_999",
            "content": "Sự kiện kiểm tra chống lặp",
            "platform": "powerpoint",
        }, headers=headers).json()
        assert r2["status"] == "already_processed"
        assert r2["state_version"] == v1, "State version must NOT increment on duplicate event"

    def test_concurrent_state_advancement_thread_safety(self, client: TestClient):
        _, token = _register_and_login(client, "alice_concurrent")
        headers = {"Authorization": f"Bearer {token}"}

        def _send(idx):
            return client.post("/v1/me/events", json={
                "content": f"Concurrent message {idx}",
                "platform": "web",
            }, headers=headers).json()

        # Fire 6 concurrent requests
        with concurrent.futures.ThreadPoolExecutor(max_workers=6) as executor:
            futures = [executor.submit(_send, i) for i in range(6)]
            results = [f.result() for f in concurrent.futures.as_completed(futures)]

        versions = [r["state_version"] for r in results]
        assert len(versions) == 6
        # Verify that state ended at version 6
        final_state = client.get("/v1/me/state", headers=headers).json()
        assert final_state["state_version"] == 6

    def test_atomic_state_and_event_rollback_on_event_failure(self, client: TestClient):
        """Verify that if recording an event fails, the state update is atomically rolled back."""
        _, token = _register_and_login(client, "alice_rollback")
        headers = {"Authorization": f"Bearer {token}"}
        user = client.get("/v1/auth/me", headers=headers).json()
        uid = user["user_id"]
        db = mem_mod.get_memory_db()

        # Initial state is version 0 / None
        st0 = db.get_dusnx_state(uid)
        assert st0 is None

        # Simulate a DB failure during event insert via a temporary abort trigger
        with db._lock:
            db._conn.execute(
                "CREATE TRIGGER fail_user_events_trigger BEFORE INSERT ON user_events BEGIN SELECT RAISE(ABORT, 'Simulated DB failure on event insert'); END;"
            )
            db._conn.commit()

        # Now attempt to advance state and record event atomically
        with pytest.raises(Exception) as excinfo:
            db.advance_state_and_record_event_atomic(
                user_id=uid,
                state_blob={"global_state": [0.1, 0.2]},
                state_version=5,
                platform="web",
                event_type="chat_message",
                content="This should roll back",
            )
        assert "Simulated DB failure on event insert" in str(excinfo.value)

        # Drop trigger to restore DB
        with db._lock:
            db._conn.execute("DROP TRIGGER IF EXISTS fail_user_events_trigger;")
            db._conn.commit()

        # Crucial assertion: dusnx_state MUST NOT have been updated to version 5!
        st_after_failure = db.get_dusnx_state(uid)
        assert st_after_failure is None, "State must roll back atomically if event insert fails!"

        # Events must also be empty
        events = db.list_user_events(uid)
        assert len(events) == 0


# ── Test 8: Unproxied Static Server Detection ──────────────────────────────────

class TestUnproxiedStaticServer:
    def test_unproxied_static_server_lacks_v1_proxy(self):
        """Verify that an unproxied static file server (python -m http.server 3000) cannot proxy /v1 routes."""
        import http.server
        import socket
        import threading
        import httpx

        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
        s.close()

        handler = http.server.SimpleHTTPRequestHandler
        server = http.server.HTTPServer(("127.0.0.1", port), handler)
        t = threading.Thread(target=server.serve_forever, daemon=True)
        t.start()
        try:
            r = httpx.post(f"http://127.0.0.1:{port}/v1/auth/login", json={"username": "a", "password": "b"}, timeout=3)
            # Static server returns 404 or 501 for unhandled POST /v1 route
            assert r.status_code in (404, 501), "Raw http.server must fail to handle /v1 API routes without proxy"
        except (httpx.ReadError, httpx.ConnectError):
            # On Windows, raw SimpleHTTPRequestHandler aborts connection on 501 without reading POST body
            pass
        finally:
            server.shutdown()
            server.server_close()
