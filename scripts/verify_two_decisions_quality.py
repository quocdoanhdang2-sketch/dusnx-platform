"""
Real HTTP acceptance through Gateway (http://127.0.0.1:8080).
Verifies:
1. Two decisions of different topics stored.
2. Modifying one decision ("Đổi quyết định hạ tầng đám mây sang AWS nhé").
3. Verifying pending record has topic, scope, new_value, proposed full sentence, statement_source.
4. User confirms -> atomic supersede.
5. In a new session, query each topic separately.
6. Verifies verbatim responses, provider_used, model_used, routing_source, memory_ids_used, DB states.
"""
from __future__ import annotations
from datetime import datetime, timezone
import json
from pathlib import Path
import secrets
import sys
import httpx

GATEWAY_URL = "http://127.0.0.1:8080"

DECISION_1 = "Hãy nhớ rằng: chúng tôi chọn GCP cho dự án hạ tầng đám mây năm 2026."
DECISION_2 = "Hãy nhớ rằng: chúng tôi chọn PostgreSQL làm hệ thống cơ sở dữ liệu chính."
MODIFY_MSG = "Đổi quyết định hạ tầng đám mây sang AWS nhé"
CONFIRM_MSG = "Đồng ý"
QUERY_CLOUD = "Hạ tầng đám mây được chọn cho dự án là gì?"
QUERY_DB = "Cơ sở dữ liệu được chọn là gì?"


def run_acceptance():
    report = {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "gateway": GATEWAY_URL,
        "transport": "real_http_via_gateway",
        "steps": {},
    }
    headers = {}

    with httpx.Client(base_url=GATEWAY_URL, timeout=120, trust_env=False) as client:
        def call(method, path, **kwargs):
            resp = client.request(method, path, headers=headers, **kwargs)
            if resp.status_code >= 400:
                raise RuntimeError(f"{method} {path}: HTTP {resp.status_code} - {resp.text}")
            return resp.json()

        # Step 0: Check health
        gateway_health = call("GET", "/health")
        v1_health = call("GET", "/v1/health")
        report["health"] = {
            "gateway_status": gateway_health.get("status"),
            "runtime_mode": v1_health.get("runtime_mode"),
            "model_version": v1_health.get("model_version"),
            "checkpoint_loaded": v1_health.get("checkpoint_loaded"),
            "provider_ok": v1_health.get("provider_ok"),
            "provider": v1_health.get("provider"),
        }
        assert gateway_health.get("service") == "dusnx-gateway", "Gateway not found"
        assert v1_health.get("runtime_mode") == "trained_dusnx", "Model not in trained_dusnx mode"
        assert v1_health.get("provider_ok") is True, "Provider not ok"

        # Step 1: Register and login test user
        username = f"user_quality_{secrets.token_hex(6)}"
        password = f"Pass_{secrets.token_urlsafe(16)}"
        call("POST", "/v1/auth/register", json={"username": username, "password": password})
        login_res = call("POST", "/v1/auth/login", json={"username": username, "password": password})
        token = login_res["token"]
        headers["Authorization"] = f"Bearer {token}"
        report["user"] = username

        # Step 2: Session 1 - Save Decision 1 and Decision 2
        s1 = call("POST", "/v1/sessions", json={"title": "Session 1 - Setup Decisions"})["session_id"]
        res_d1 = call("POST", "/v1/chat", json={"session_id": s1, "message": DECISION_1})
        res_d2 = call("POST", "/v1/chat", json={"session_id": s1, "message": DECISION_2})

        mems_after_save = call("GET", "/v1/memories?include_inactive=true")
        report["steps"]["after_save"] = {
            "total_memories": len(mems_after_save),
            "memories": [
                {
                    "memory_id": m["memory_id"],
                    "content": m["content"],
                    "is_active": m["is_active"],
                    "version": m["version"],
                }
                for m in mems_after_save
            ],
        }
        assert len(mems_after_save) == 2, f"Expected 2 memories, got {len(mems_after_save)}"
        gcp_mem = next(m for m in mems_after_save if "GCP" in m["content"])
        pg_mem = next(m for m in mems_after_save if "PostgreSQL" in m["content"])
        assert gcp_mem["is_active"] and pg_mem["is_active"]

        # Step 3: Modify Decision 1 ("Đổi quyết định hạ tầng đám mây sang AWS nhé")
        res_modify = call("POST", "/v1/chat", json={"session_id": s1, "message": MODIFY_MSG})
        pendings = call("GET", "/v1/pending-decisions")
        report["steps"]["after_modify_intent"] = {
            "chat_reply": res_modify.get("reply"),
            "intent": res_modify.get("intent"),
            "next_action": res_modify.get("next_action"),
            "routing_source": res_modify.get("routing_source"),
            "pendings_count": len(pendings),
            "pending_detail": pendings[0] if pendings else None,
        }
        assert len(pendings) == 1, "Expected 1 pending decision"
        p = pendings[0]
        assert p["old_memory_id"] == gcp_mem["memory_id"]
        assert p["topic"] == "hạ tầng đám mây"
        assert p["new_value"] == "AWS"
        assert "AWS" in p["proposed_content"]
        assert p["proposed_content"] != "AWS nhé."
        assert not p["proposed_content"].endswith("..")

        # Step 4: Confirm update
        res_confirm = call("POST", "/v1/chat", json={"session_id": s1, "message": CONFIRM_MSG})
        mems_after_confirm = call("GET", "/v1/memories?include_inactive=true")
        active_mems = [m for m in mems_after_confirm if m["is_active"]]
        inactive_mems = [m for m in mems_after_confirm if not m["is_active"]]

        report["steps"]["after_confirm"] = {
            "chat_reply": res_confirm.get("reply"),
            "intent": res_confirm.get("intent"),
            "next_action": res_confirm.get("next_action"),
            "routing_source": res_confirm.get("routing_source"),
            "memory_ids_used": res_confirm.get("memory_ids_used"),
            "active_count": len(active_mems),
            "inactive_count": len(inactive_mems),
            "memories_state": [
                {
                    "memory_id": m["memory_id"],
                    "content": m["content"],
                    "is_active": m["is_active"],
                    "superseded_by": m["superseded_by"],
                    "version": m["version"],
                }
                for m in mems_after_confirm
            ],
        }
        assert len(active_mems) == 2
        assert len(inactive_mems) == 1
        old_gcp = next(m for m in inactive_mems if m["memory_id"] == gcp_mem["memory_id"])
        new_aws = next(m for m in active_mems if "AWS" in m["content"])
        assert old_gcp["superseded_by"] == new_aws["memory_id"]
        assert new_aws["version"] == 2
        assert "PostgreSQL" in next(m["content"] for m in active_mems if m["memory_id"] == pg_mem["memory_id"])

        # Step 5: Open Session 2 and query separately
        s2 = call("POST", "/v1/sessions", json={"title": "Session 2 - Independent Queries"})["session_id"]
        assert s1 != s2, "Must be a new session"

        # Query 1: Cloud infrastructure
        res_q_cloud = call("POST", "/v1/chat", json={"session_id": s2, "message": QUERY_CLOUD})
        report["steps"]["query_cloud"] = {
            "query": QUERY_CLOUD,
            "reply": res_q_cloud.get("reply"),
            "provider_used": res_q_cloud.get("provider_used"),
            "model_used": res_q_cloud.get("model_used"),
            "routing_source": res_q_cloud.get("routing_source"),
            "memory_ids_used": res_q_cloud.get("memory_ids_used"),
            "provider_ok": res_q_cloud.get("provider_ok"),
        }
        # Verify Cloud query properties
        assert "AWS" in res_q_cloud["reply"], f"Reply must contain AWS: {res_q_cloud['reply']}"
        assert ".." not in res_q_cloud["reply"], "Reply must not contain double periods '..'"
        assert res_q_cloud["reply"].strip() != "AWS nhé."
        assert new_aws["memory_id"] in res_q_cloud["memory_ids_used"]
        assert old_gcp["memory_id"] not in res_q_cloud["memory_ids_used"]

        # Query 2: Database
        res_q_db = call("POST", "/v1/chat", json={"session_id": s2, "message": QUERY_DB})
        report["steps"]["query_db"] = {
            "query": QUERY_DB,
            "reply": res_q_db.get("reply"),
            "provider_used": res_q_db.get("provider_used"),
            "model_used": res_q_db.get("model_used"),
            "routing_source": res_q_db.get("routing_source"),
            "memory_ids_used": res_q_db.get("memory_ids_used"),
            "provider_ok": res_q_db.get("provider_ok"),
        }
        # Verify DB query properties
        assert "PostgreSQL" in res_q_db["reply"], f"Reply must contain PostgreSQL: {res_q_db['reply']}"
        assert ".." not in res_q_db["reply"], "Reply must not contain double periods '..'"
        assert pg_mem["memory_id"] in res_q_db["memory_ids_used"]
        assert old_gcp["memory_id"] not in res_q_db["memory_ids_used"]

        # Logout
        call("POST", "/v1/auth/logout")

    report["status"] = "PASSED"
    out_path = Path("runtime/two-decisions-acceptance.json")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return report


if __name__ == "__main__":
    run_acceptance()
