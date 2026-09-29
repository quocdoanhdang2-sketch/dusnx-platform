"""
Tests for Memory Quality and Disambiguation in DUSN-X
Covers:
- Full sentence preservation on decision supersede (GCP -> AWS, non-cloud entities)
- Coexistence of multiple independent active decisions queried by topic
- Disambiguation prompts when multiple decisions match or modify is ambiguous
- Rejection, ambiguous confirmation, and idempotent retry without duplication
- Multi-session, multi-user isolation
- Clean answer formatting without double punctuation or repeated prefixes
"""
from __future__ import annotations

import os
from pathlib import Path
import pytest
from fastapi.testclient import TestClient

from apps.ai_api.main import app
import apps.ai_api.auth as auth_mod
import apps.ai_api.memory as mem_mod
from apps.ai_api.grounding import format_memory_answer, memory_answer_with_match


@pytest.fixture(autouse=True)
def isolated_env(tmp_path, monkeypatch):
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
    return TestClient(app)


def _register_and_login(client: TestClient, username: str) -> tuple[str, str]:
    r = client.post("/v1/auth/register", json={"username": username, "password": "Password123!"})
    assert r.status_code == 201, r.text
    user_id = r.json()["user_id"]
    r2 = client.post("/v1/auth/login", json={"username": username, "password": "Password123!"})
    assert r2.status_code == 200, r2.text
    return user_id, r2.json()["token"]


def test_gcp_to_aws_supersede_full_content_and_inactive_old(client: TestClient):
    """GCP -> AWS: proposed content has full sentence, old record is superseded & inactive."""
    user_id, token = _register_and_login(client, "test_gcp_aws")
    headers = {"Authorization": f"Bearer {token}"}
    s_resp = client.post("/v1/sessions", headers=headers, json={"title": "Session 1"})
    sid1 = s_resp.json()["session_id"]

    # Step 1: Save GCP decision
    r1 = client.post("/v1/chat", headers=headers, json={
        "session_id": sid1,
        "message": "Ghi nhớ quyết định: Chúng tôi chọn GCP cho dự án hạ tầng đám mây năm 2026."
    })
    assert r1.status_code == 200
    assert r1.json()["intent"] == "memory_create"

    # Step 2: Request change to AWS
    r2 = client.post("/v1/chat", headers=headers, json={
        "session_id": sid1,
        "message": "Đổi quyết định hạ tầng đám mây sang AWS nhé."
    })
    assert r2.status_code == 200
    r2_data = r2.json()
    assert r2_data["intent"] == "decision_modify_intent"
    assert r2_data["next_action"] == "await_confirm"
    # Ensure confirmation dialog shows full proposed content, not just "AWS nhé."
    assert "Chúng tôi chọn AWS cho dự án hạ tầng đám mây năm 2026" in r2_data["reply"]
    assert "AWS nhé." not in r2_data["reply"]

    # Verify pending record fields in DB
    db = mem_mod.get_memory_db()
    pending = db.get_session_pending_decision(user_id, sid1)
    assert pending is not None
    assert pending["status"] == "awaiting_confirm"
    assert pending["old_content"] == "Chúng tôi chọn GCP cho dự án hạ tầng đám mây năm 2026"
    assert pending["proposed_content"] == "Chúng tôi chọn AWS cho dự án hạ tầng đám mây năm 2026"
    assert pending["new_value"] == "AWS"
    assert "hạ tầng đám mây" in pending["topic"]

    # Step 3: Confirm change
    r3 = client.post("/v1/chat", headers=headers, json={
        "session_id": sid1,
        "message": "Có, tôi xác nhận đổi."
    })
    assert r3.status_code == 200
    r3_data = r3.json()
    assert r3_data["intent"] == "decision_update"
    assert "Chúng tôi chọn AWS cho dự án hạ tầng đám mây năm 2026" in r3_data["reply"]

    # Verify SQLite state
    memories = db.list_memories(user_id, include_inactive=True)
    assert len(memories) == 2
    old_m = next(m for m in memories if m["is_active"] == 0)
    new_m = next(m for m in memories if m["is_active"] == 1)

    assert "GCP" in old_m["content"]
    assert old_m["superseded_by"] == new_m["memory_id"]
    assert new_m["content"] == "Chúng tôi chọn AWS cho dự án hạ tầng đám mây năm 2026"
    assert new_m["version"] == 2
    assert new_m["superseded_by"] is None

    # Step 4: Open new session and query current decision
    s_resp2 = client.post("/v1/sessions", headers=headers, json={"title": "Session 2"})
    sid2 = s_resp2.json()["session_id"]
    r4 = client.post("/v1/chat", headers=headers, json={
        "session_id": sid2,
        "message": "Quyết định hạ tầng đám mây năm 2026 hiện hành của tôi là gì?"
    })
    assert r4.status_code == 200
    r4_data = r4.json()
    assert "Chúng tôi chọn AWS cho dự án hạ tầng đám mây năm 2026" in r4_data["reply"]
    assert "GCP" not in r4_data["reply"]
    assert not r4_data["reply"].endswith("..")
    assert r4_data["memory_ids_used"] == [new_m["memory_id"]]


def test_two_independent_decisions_coexist_and_query_by_topic(client: TestClient):
    """Two independent decisions coexist; queries by topic retrieve the exact correct decision."""
    user_id, token = _register_and_login(client, "test_two_decisions")
    headers = {"Authorization": f"Bearer {token}"}
    sid = client.post("/v1/sessions", headers=headers, json={"title": "Session"}).json()["session_id"]

    # Save Decision 1: Cloud
    client.post("/v1/chat", headers=headers, json={
        "session_id": sid,
        "message": "Ghi nhớ quyết định: Chúng tôi chọn AWS cho dự án hạ tầng đám mây năm 2026."
    })
    # Save Decision 2: Database
    client.post("/v1/chat", headers=headers, json={
        "session_id": sid,
        "message": "Ghi nhớ quyết định: Công ty sử dụng PostgreSQL làm cơ sở dữ liệu chính từ Q3."
    })

    # Query 1: Cloud
    q1 = client.post("/v1/chat", headers=headers, json={
        "session_id": sid,
        "message": "Quyết định hạ tầng đám mây năm 2026 là gì?"
    }).json()
    assert "AWS" in q1["reply"]
    assert "PostgreSQL" not in q1["reply"]

    # Query 2: Database
    q2 = client.post("/v1/chat", headers=headers, json={
        "session_id": sid,
        "message": "Quyết định cơ sở dữ liệu chính hiện tại là gì?"
    }).json()
    assert "PostgreSQL" in q2["reply"]
    assert "AWS" not in q2["reply"]


def test_ambiguous_modify_request_asks_clarification(client: TestClient):
    """When multiple decisions match or modify is ambiguous, asks clarification without guessing."""
    user_id, token = _register_and_login(client, "test_ambig_modify")
    headers = {"Authorization": f"Bearer {token}"}
    sid = client.post("/v1/sessions", headers=headers, json={"title": "Session"}).json()["session_id"]

    # User has two decisions
    client.post("/v1/chat", headers=headers, json={
        "session_id": sid,
        "message": "Ghi nhớ quyết định: Chọn GCP cho hạ tầng dev."
    })
    client.post("/v1/chat", headers=headers, json={
        "session_id": sid,
        "message": "Ghi nhớ quyết định: Chọn Azure cho hạ tầng prod."
    })

    # User sends ambiguous modify request matching both
    r = client.post("/v1/chat", headers=headers, json={
        "session_id": sid,
        "message": "Đổi quyết định hạ tầng sang AWS nhé."
    }).json()

    assert r["intent"] == "clarify_ambiguous_decision"
    assert r["next_action"] == "clarify"
    assert "nhiều quyết định" in r["reply"]
    # Check no pending decision was created
    db = mem_mod.get_memory_db()
    assert db.get_session_pending_decision(user_id, sid) is None


def test_reject_and_ambiguous_confirm_and_retry(client: TestClient):
    """Test rejection preserves memory, ambiguous confirm keeps waiting, and retry is idempotent."""
    user_id, token = _register_and_login(client, "test_confirm_flows")
    headers = {"Authorization": f"Bearer {token}"}
    sid = client.post("/v1/sessions", headers=headers, json={"title": "Session"}).json()["session_id"]
    db = mem_mod.get_memory_db()

    # Create initial decision
    client.post("/v1/chat", headers=headers, json={
        "session_id": sid,
        "message": "Ghi nhớ quyết định: Dự án dùng FastAPI cho backend."
    })
    init_mem = db.list_memories(user_id)[0]

    # Trigger modify request
    client.post("/v1/chat", headers=headers, json={
        "session_id": sid,
        "message": "Đổi backend sang Django nhé."
    })
    assert db.get_session_pending_decision(user_id, sid) is not None

    # Ambiguous reply -> keeps waiting without touching memory
    r_unclear = client.post("/v1/chat", headers=headers, json={
        "session_id": sid,
        "message": "Tôi đang suy nghĩ, chưa chắc chắn"
    }).json()
    assert r_unclear["intent"] == "awaiting_confirm"
    assert "chưa rõ ý bạn" in r_unclear["reply"].lower()
    assert db.get_memory(user_id, init_mem["memory_id"])["is_active"] == 1
    assert db.get_session_pending_decision(user_id, sid) is not None

    # Reject -> cancels pending and keeps old memory active
    r_cancel = client.post("/v1/chat", headers=headers, json={
        "session_id": sid,
        "message": "Không đồng ý, giữ nguyên"
    }).json()
    assert r_cancel["intent"] == "decision_update_cancelled"
    assert db.get_memory(user_id, init_mem["memory_id"])["is_active"] == 1
    assert db.get_session_pending_decision(user_id, sid) is None

    # New modify request + confirm
    client.post("/v1/chat", headers=headers, json={
        "session_id": sid,
        "message": "Đổi backend sang Tornado nhé."
    })
    r_confirm = client.post("/v1/chat", headers=headers, json={
        "session_id": sid,
        "message": "Đồng ý"
    }).json()
    assert r_confirm["intent"] == "decision_update"

    # Idempotent retry: repeat confirmation request
    r_retry = client.post("/v1/chat", headers=headers, json={
        "session_id": sid,
        "message": "Đồng ý",
        "is_retry": True,
    }).json()
    assert r_retry["intent"] == "decision_update"

    # Ensure no duplicate version or record was created
    all_m = db.list_memories(user_id, include_inactive=True)
    active_m = [m for m in all_m if m["is_active"] == 1]
    assert len(active_m) == 1
    assert active_m[0]["version"] == 2
    assert "Tornado" in active_m[0]["content"]


def test_multi_user_multi_session_no_leakage(client: TestClient):
    """User A and User B operate in multiple sessions with zero cross-user memory leakage."""
    uA, tA = _register_and_login(client, "user_alice")
    uB, tB = _register_and_login(client, "user_bob")
    hA, hB = {"Authorization": f"Bearer {tA}"}, {"Authorization": f"Bearer {tB}"}

    sA1 = client.post("/v1/sessions", headers=hA, json={"title": "A1"}).json()["session_id"]
    sB1 = client.post("/v1/sessions", headers=hB, json={"title": "B1"}).json()["session_id"]

    client.post("/v1/chat", headers=hA, json={
        "session_id": sA1,
        "message": "Ghi nhớ quyết định: Dự án A dùng Dragonfly."
    })
    client.post("/v1/chat", headers=hB, json={
        "session_id": sB1,
        "message": "Ghi nhớ quyết định: Dự án B dùng Memcached."
    })

    # Bob queries in a new session B2
    sB2 = client.post("/v1/sessions", headers=hB, json={"title": "B2"}).json()["session_id"]
    qB = client.post("/v1/chat", headers=hB, json={
        "session_id": sB2,
        "message": "Quyết định dự án của tôi là gì?"
    }).json()

    assert "Memcached" in qB["reply"]
    assert "Dragonfly" not in qB["reply"]


def test_answer_formatting_no_double_punctuation_and_attribution():
    """Verify format_memory_answer prevents double punctuation and repeated prefixes."""
    assert format_memory_answer("AWS nhé.") == "Theo trí nhớ đang hiệu lực: AWS nhé."
    assert format_memory_answer("Chúng tôi dùng PostgreSQL...") == "Theo trí nhớ đang hiệu lực: Chúng tôi dùng PostgreSQL."
    assert format_memory_answer("Theo trí nhớ đang hiệu lực: Dùng Redis.") == "Theo trí nhớ đang hiệu lực: Dùng Redis."
    assert format_memory_answer("Dự án chọn Linode") == "Theo trí nhớ đang hiệu lực: Dự án chọn Linode."

    # Attribution with match
    mems = [{"memory_id": "mem_123", "content": "Chọn AWS"}]
    ans, matched = memory_answer_with_match("Quyết định của tôi là gì?", mems)
    assert ans == "Theo trí nhớ đang hiệu lực: Chọn AWS."
    assert matched is not None and matched["memory_id"] == "mem_123"


def test_general_entities_non_cloud_substitution(client: TestClient):
    """Verify general substitution on diverse entities (Database, UI framework, Marketing)."""
    user_id, token = _register_and_login(client, "test_general_entities")
    headers = {"Authorization": f"Bearer {token}"}
    sid = client.post("/v1/sessions", headers=headers, json={"title": "Session"}).json()["session_id"]

    # Test PostgreSQL -> MongoDB
    client.post("/v1/chat", headers=headers, json={
        "session_id": sid,
        "message": "Ghi nhớ quyết định: Công ty sử dụng PostgreSQL làm cơ sở dữ liệu chính từ Q3."
    })
    client.post("/v1/chat", headers=headers, json={
        "session_id": sid,
        "message": "Đổi cơ sở dữ liệu chính sang MongoDB nhé."
    })
    r_conf = client.post("/v1/chat", headers=headers, json={
        "session_id": sid,
        "message": "Xác nhận đổi"
    }).json()

    assert "Công ty sử dụng MongoDB làm cơ sở dữ liệu chính từ Q3" in r_conf["reply"]

    # Verify query
    q = client.post("/v1/chat", headers=headers, json={
        "session_id": sid,
        "message": "Cơ sở dữ liệu chính hiện tại là gì?"
    }).json()
    assert "MongoDB" in q["reply"]
    assert "PostgreSQL" not in q["reply"]
    assert not q["reply"].endswith("..")
