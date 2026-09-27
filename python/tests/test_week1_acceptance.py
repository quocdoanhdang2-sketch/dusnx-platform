"""
DUSN-X Week 1 Acceptance Tests
================================
Tests the core acceptance criteria from the spec:
1. Decision update: old decision superseded, new one returned
2. Cross-session memory: new session sees latest decisions
3. User isolation: User B cannot read User A's memories
4. Restart persistence: session and memory survive app restart
5. Memory edit/delete cycle
6. Provider error handling: clear error, not fake success
"""
from __future__ import annotations

import secrets
import os
import sys
from pathlib import Path

import pytest

# Add repo root to path so scripts.validate_data can be imported
REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

# Use a separate test DB to avoid polluting production data
TEST_DATA_DIR = Path(__file__).parent / "test_runtime"

@pytest.fixture(autouse=True)
def isolated_db(tmp_path, monkeypatch):
    """Each test gets its own isolated database directory."""
    monkeypatch.setenv("DUSNX_DATA_DIR", str(tmp_path))
    # Close and reset singletons so each test starts with a fresh DB in tmp_path
    import apps.ai_api.auth as auth_mod
    import apps.ai_api.memory as mem_mod
    if auth_mod._auth_db is not None:
        auth_mod._auth_db.close()
        auth_mod._auth_db = None
    if mem_mod._memory_db is not None:
        mem_mod._memory_db.close()
        mem_mod._memory_db = None
    yield
    # Cleanup after test
    if auth_mod._auth_db is not None:
        auth_mod._auth_db.close()
        auth_mod._auth_db = None
    if mem_mod._memory_db is not None:
        mem_mod._memory_db.close()
        mem_mod._memory_db = None


# ── Auth Tests ─────────────────────────────────────────────────────────────────

class TestAuth:
    def test_register_and_login(self):
        from apps.ai_api.auth import get_auth_db
        db = get_auth_db()
        user = db.register("alice_test", "password123")
        assert user["username"] == "alice_test"
        assert "user_id" in user

    def test_register_duplicate_raises(self):
        from apps.ai_api.auth import get_auth_db
        db = get_auth_db()
        db.register("bob_test", "password123")
        with pytest.raises(ValueError, match="already exists"):
            db.register("bob_test", "different_pass")

    def test_login_returns_token(self):
        from apps.ai_api.auth import get_auth_db
        db = get_auth_db()
        db.register("charlie_test", "password123")
        token = db.login("charlie_test", "password123")
        assert token is not None
        assert len(token) > 20

    def test_wrong_password_returns_none(self):
        from apps.ai_api.auth import get_auth_db
        db = get_auth_db()
        db.register("dave_test", "password123")
        token = db.login("dave_test", "wrongpassword")
        assert token is None

    def test_verify_valid_token(self):
        from apps.ai_api.auth import get_auth_db
        db = get_auth_db()
        db.register("eve_test", "password123")
        token = db.login("eve_test", "password123")
        user_info = db.verify_token(token)
        assert user_info is not None
        assert user_info["username"] == "eve_test"

    def test_verify_invalid_token(self):
        from apps.ai_api.auth import get_auth_db
        db = get_auth_db()
        result = db.verify_token("nonexistent_token_xyz")
        assert result is None

    def test_logout_invalidates_token(self):
        from apps.ai_api.auth import get_auth_db
        db = get_auth_db()
        db.register("frank_test", "password123")
        token = db.login("frank_test", "password123")
        db.logout(token)
        assert db.verify_token(token) is None

    def test_password_not_stored_plaintext(self):
        """Verify password is not stored in plaintext in the database."""
        from apps.ai_api.auth import get_auth_db
        import os
        db = get_auth_db()
        db.register("grace_test", "MySecret123")
        db_path = db._db_path
        import sqlite3
        # Open a second connection to verify storage
        conn2 = sqlite3.connect(str(db_path))
        rows = conn2.execute("SELECT password_hash, salt FROM users WHERE username='grace_test'").fetchall()
        conn2.close()
        assert rows, "User should exist in DB"
        pw_hash, salt = rows[0]
        assert "MySecret123" not in pw_hash
        assert "MySecret123" not in salt


# ── Memory Tests ───────────────────────────────────────────────────────────────

class TestMemory:
    def _make_user(self):
        from apps.ai_api.auth import get_auth_db
        db = get_auth_db()
        username = f"user_{secrets.token_hex(4)}"
        db.register(username, "password123")
        token = db.login(username, "password123")
        user_info = db.verify_token(token)
        return user_info["user_id"]

    def test_create_and_read_memory(self):
        from apps.ai_api.memory import get_memory_db
        db = get_memory_db()
        uid = self._make_user()
        mem = db.create_memory(uid, "goal", "Build a personalized chatbot")
        assert mem["memory_id"] is not None
        assert mem["is_active"] is True
        assert mem["version"] == 1
        assert mem["content"] == "Build a personalized chatbot"

    def test_decision_supersede_cycle(self):
        """
        ACCEPTANCE TEST 1 & 2:
        User says "I'm building chatbot with Zalo" → then "Remove Zalo, focus on memory"
        → New session: "What am I prioritizing?" → should NOT include Zalo as active plan.
        """
        from apps.ai_api.memory import get_memory_db
        db = get_memory_db()
        uid = self._make_user()

        # Step 1: User establishes decision
        mem1 = db.create_memory(
            uid, "decision",
            "Tôi làm dự án chatbot cá nhân hóa, dự kiến thêm gọi Zalo tự động.",
            source_session="session_a",
        )
        assert mem1["is_active"] is True
        assert mem1["version"] == 1

        # Step 2: User revises decision
        mem2 = db.update_memory(
            uid, mem1["memory_id"],
            "Bỏ gọi Zalo tự động; tập trung trí nhớ xuyên ứng dụng.",
            source_session="session_b",
        )
        assert mem2 is not None
        assert mem2["is_active"] is True
        assert mem2["version"] == 2

        # Step 3: Old decision is now inactive
        mem1_reloaded = db.get_memory(uid, mem1["memory_id"])
        assert mem1_reloaded["is_active"] is False
        assert mem1_reloaded["superseded_by"] == mem2["memory_id"]

        # Step 4: Active memories do NOT include old Zalo decision
        active = db.list_memories(uid, include_inactive=False)
        active_contents = [m["content"] for m in active]
        assert not any("Zalo tự động" in c and "dự kiến thêm" in c for c in active_contents), \
            "Old Zalo plan should not appear in active memories"
        assert any("trí nhớ xuyên ứng dụng" in c for c in active_contents), \
            "New decision should be in active memories"

        # Step 5: Including inactive shows both
        all_mems = db.list_memories(uid, include_inactive=True)
        assert len(all_mems) == 2
        inactive = [m for m in all_mems if not m["is_active"]]
        assert len(inactive) == 1
        assert "Zalo tự động" in inactive[0]["content"]

    def test_user_isolation(self):
        """
        ACCEPTANCE TEST 5:
        User B cannot read User A's memories even by guessing IDs.
        """
        from apps.ai_api.memory import get_memory_db
        db = get_memory_db()
        uid_a = self._make_user()
        uid_b = self._make_user()

        # User A creates a memory
        mem_a = db.create_memory(uid_a, "secret", "User A's private information")

        # User B cannot read it even with the correct memory_id
        result = db.get_memory(uid_b, mem_a["memory_id"])
        assert result is None, "User B should not be able to read User A's memory"

        # User B gets empty list
        b_memories = db.list_memories(uid_b)
        assert len(b_memories) == 0

    def test_memory_delete_soft(self):
        """Delete should deactivate, not erase history."""
        from apps.ai_api.memory import get_memory_db
        db = get_memory_db()
        uid = self._make_user()
        mem = db.create_memory(uid, "preference", "I prefer dark mode")
        ok = db.delete_memory(uid, mem["memory_id"])
        assert ok is True

        # Memory still exists but is inactive
        reloaded = db.get_memory(uid, mem["memory_id"])
        assert reloaded is not None
        assert reloaded["is_active"] is False

        # Does not appear in active list
        active = db.list_memories(uid, include_inactive=False)
        assert len(active) == 0

        # Appears in full history
        all_mems = db.list_memories(uid, include_inactive=True)
        assert len(all_mems) == 1

    def test_user_b_cannot_delete_user_a_memory(self):
        """User B cannot delete User A's memory using the memory_id."""
        from apps.ai_api.memory import get_memory_db
        db = get_memory_db()
        uid_a = self._make_user()
        uid_b = self._make_user()

        mem_a = db.create_memory(uid_a, "goal", "A private goal")
        ok = db.delete_memory(uid_b, mem_a["memory_id"])
        assert ok is False, "User B should not be able to delete User A's memory"

        # Memory still active for User A
        reloaded = db.get_memory(uid_a, mem_a["memory_id"])
        assert reloaded["is_active"] is True

    def test_memory_edit_after_restart(self, tmp_path):
        """Memory persists across DB re-instantiation (simulates restart)."""
        from apps.ai_api.memory import MemoryDB
        db = MemoryDB()
        uid = secrets.token_hex(16)

        mem = db.create_memory(uid, "project_fact", "DUSN-X is my main project")
        mem_id = mem["memory_id"]

        # Re-instantiate DB (simulates restart)
        db2 = MemoryDB()
        loaded = db2.get_memory(uid, mem_id)
        assert loaded is not None
        assert loaded["content"] == "DUSN-X is my main project"
        assert loaded["is_active"] is True


# ── Session Tests ──────────────────────────────────────────────────────────────

class TestSessions:
    def _make_user(self):
        from apps.ai_api.auth import get_auth_db
        db = get_auth_db()
        username = f"user_{secrets.token_hex(4)}"
        db.register(username, "password123")
        token = db.login(username, "password123")
        return db.verify_token(token)["user_id"]

    def test_create_and_list_sessions(self):
        from apps.ai_api.memory import get_memory_db
        db = get_memory_db()
        uid = self._make_user()
        s1 = db.create_session(uid, "Session One")
        s2 = db.create_session(uid, "Session Two")
        sessions = db.list_sessions(uid)
        assert len(sessions) >= 2
        ids = [s["session_id"] for s in sessions]
        assert s1["session_id"] in ids
        assert s2["session_id"] in ids

    def test_session_isolation_between_users(self):
        """User B cannot access User A's session."""
        from apps.ai_api.memory import get_memory_db
        db = get_memory_db()
        uid_a = self._make_user()
        uid_b = self._make_user()
        sess_a = db.create_session(uid_a, "A's private session")

        result = db.get_session(uid_b, sess_a["session_id"])
        assert result is None

    def test_messages_persist(self):
        from apps.ai_api.memory import get_memory_db
        db = get_memory_db()
        uid = self._make_user()
        sess = db.create_session(uid, "Test session")
        db.append_message(sess["session_id"], uid, "user", "Hello DUSN-X")
        db.append_message(sess["session_id"], uid, "assistant", "Hello! How can I help?")

        messages = db.get_messages(uid, sess["session_id"])
        assert len(messages) == 2
        assert messages[0]["role"] == "user"
        assert messages[0]["content"] == "Hello DUSN-X"
        assert messages[1]["role"] == "assistant"

    def test_messages_survive_restart(self, tmp_path):
        """Messages persist across DB re-instantiation."""
        from apps.ai_api.memory import MemoryDB
        db = MemoryDB()
        uid = secrets.token_hex(16)
        sess = db.create_session(uid, "Persistence test")
        db.append_message(sess["session_id"], uid, "user", "Persist this message")

        db2 = MemoryDB()
        msgs = db2.get_messages(uid, sess["session_id"])
        assert len(msgs) == 1
        assert msgs[0]["content"] == "Persist this message"


# ── Project Tests ──────────────────────────────────────────────────────────────

class TestProjects:
    def _make_user(self):
        from apps.ai_api.auth import get_auth_db
        db = get_auth_db()
        username = f"user_{secrets.token_hex(4)}"
        db.register(username, "password123")
        token = db.login(username, "password123")
        return db.verify_token(token)["user_id"]

    def test_project_scoped_memories(self):
        """Memories can be scoped to a project and filtered."""
        from apps.ai_api.memory import get_memory_db
        db = get_memory_db()
        uid = self._make_user()
        proj = db.create_project(uid, "Chatbot Project")
        pid = proj["project_id"]

        db.create_memory(uid, "goal", "Build chatbot", project_id=pid)
        db.create_memory(uid, "preference", "Global pref — no project scope")

        proj_memories = db.list_memories(uid, project_id=pid)
        assert len(proj_memories) == 1
        assert proj_memories[0]["project_id"] == pid

        all_active = db.list_memories(uid)
        assert len(all_active) == 2

    def test_project_decisions_supersede(self):
        """Decisions in a project correctly supersede each other."""
        from apps.ai_api.memory import get_memory_db
        db = get_memory_db()
        uid = self._make_user()
        proj = db.create_project(uid, "Test Project")
        pid = proj["project_id"]

        d1 = db.create_memory(uid, "decision", "Use Zalo", project_id=pid)
        d2 = db.update_memory(uid, d1["memory_id"], "Drop Zalo, use web only")

        active = db.list_memories(uid, project_id=pid, include_inactive=False)
        assert len(active) == 1
        assert "web only" in active[0]["content"]

        # Old decision still accessible in full history
        all_decisions = db.list_memories(uid, project_id=None, include_inactive=True)
        inactive = [m for m in all_decisions if not m["is_active"]]
        assert any("Zalo" in m["content"] for m in inactive)


# ── Data Validator Tests ───────────────────────────────────────────────────────

class TestDataValidator:
    """Tests for the training data validator (Section 5 / Acceptance 7)."""

    def _make_valid_event(self, uid="user_1", intent="chat", agent="conversation", action="reply", platform="web"):
        return {
            "global_user_id": uid,
            "event_time_utc": "2024-01-01T10:00:00Z",
            "platform": platform,
            "content": "hello world",
            "intent_label": intent,
            "selected_agent": agent,
            "next_action_label": action,
            "feedback_value": 0.0,
        }

    def _write_jsonl(self, tmp_path, rows):
        import json
        p = tmp_path / "test_data.jsonl"
        with open(p, "w") as f:
            for row in rows:
                f.write(json.dumps(row) + "\n")
        return p

    def test_valid_data_passes(self, tmp_path):
        """Valid data passes validation with exit code 0."""
        from scripts.validate_data import validate
        rows = [self._make_valid_event(uid=f"user_{i}") for i in range(10)]
        p = self._write_jsonl(tmp_path, rows)
        code = validate(p)
        assert code == 0, "Valid data should pass"

    def test_invalid_intent_label_fails(self, tmp_path):
        """Invalid intent label should fail validation."""
        from scripts.validate_data import validate
        rows = [self._make_valid_event(intent="INVALID_INTENT")]
        p = self._write_jsonl(tmp_path, rows)
        code = validate(p)
        assert code == 1, "Invalid intent should fail"

    def test_invalid_platform_fails(self, tmp_path):
        """Invalid platform should fail validation."""
        from scripts.validate_data import validate
        rows = [self._make_valid_event(platform="twitter")]
        p = self._write_jsonl(tmp_path, rows)
        code = validate(p)
        assert code == 1, "Invalid platform should fail"

    def test_future_feedback_warning(self, tmp_path):
        """Non-zero feedback on first event generates a warning."""
        from scripts.validate_data import validate
        import json
        rows = [
            {**self._make_valid_event(uid="user_1"), "feedback_value": 1.0},  # first event — suspicious
            {**self._make_valid_event(uid="user_1"), "event_time_utc": "2024-01-01T11:00:00Z"},
        ]
        p = self._write_jsonl(tmp_path, rows)
        code = validate(p)
        # Should be 0 (warning only, not error) or 2 in strict mode
        assert code in (0, 2), "Future feedback should generate warning, not block training"

    def test_out_of_order_timestamps_fails(self, tmp_path):
        """Out-of-order timestamps for a user should fail."""
        from scripts.validate_data import validate
        import json
        rows = [
            {**self._make_valid_event(uid="user_1"), "event_time_utc": "2024-01-01T12:00:00Z"},
            {**self._make_valid_event(uid="user_1"), "event_time_utc": "2024-01-01T10:00:00Z"},  # earlier!
        ]
        p = self._write_jsonl(tmp_path, rows)
        code = validate(p)
        assert code == 1, "Out-of-order timestamps should fail"

    def test_missing_required_field_fails(self, tmp_path):
        """Missing required field should fail."""
        from scripts.validate_data import validate
        rows = [{"global_user_id": "u1", "content": "hello"}]  # missing many fields
        p = self._write_jsonl(tmp_path, rows)
        code = validate(p)
        assert code == 1

    def test_valid_data_trains_successfully(self, tmp_path):
        """Valid fixture allows the dataset loader to run without error."""
        import json
        from dusnx_core.config import ModelConfig
        from dusnx_core.dataset import SequenceWindowDataset

        # Create minimal valid dataset (2 events for 1 user)
        rows = []
        for i in range(6):
            rows.append({
                "global_user_id": "test_user_train",
                "event_time_utc": f"2024-01-0{i+1}T10:00:00Z",
                "platform": "web",
                "content": f"message number {i}",
                "intent_label": "chat",
                "selected_agent": "conversation",
                "next_action_label": "reply",
                "feedback_value": 0.0,
            })

        cfg = ModelConfig()
        ds = SequenceWindowDataset(rows, cfg, sequence_len=4, stride=2)
        assert len(ds) > 0, "Should have at least one sample"
        sample = ds[0]
        assert "token_ids" in sample
        assert "intent" in sample
