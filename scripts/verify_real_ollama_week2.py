"""Real HTTP acceptance through localhost:8080. No TestClient, secrets or raw auth logs."""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import secrets
import sys
import httpx

GATEWAY_URL = "http://127.0.0.1:8080"
REMEMBER = "Hãy nhớ rằng quyết định của tôi là sử dụng PostgreSQL cho cơ sở dữ liệu."
CHANGE = "Đổi PostgreSQL sang MongoDB"
CONFIRM = "Đồng ý"
QUERY = "Cơ sở dữ liệu của dự án này hiện tại là gì?"


def check_final(reply, memories, old_id):
    active = [m for m in memories if m["is_active"]]
    old = next((m for m in memories if m["memory_id"] == old_id), None)
    text = reply.get("reply", "").casefold()
    checks = {
        "provider_ok": reply.get("provider_ok") is True,
        "grounded_source": (reply.get("response_source") == "grounded_template"
                            and reply.get("provider_called") is False
                            and reply.get("provider_used") is None and reply.get("model_used") is None),
        "mongodb_active": len(active) == 1 and "mongodb" in active[0]["content"].casefold(),
        "postgresql_superseded": old is not None and not old["is_active"],
        "active_memory_used": len(active) == 1 and active[0]["memory_id"] in reply.get("memory_ids_used", []),
        "old_memory_not_used": old_id not in reply.get("memory_ids_used", []),
        # Conservative automatic criterion; semantic interpretation also requires UI review.
        "answer_mongodb_only": "mongodb" in text and "postgresql" not in text,
    }
    return checks


def run_verification(output=Path("runtime/week2-http.json")):
    report = {"timestamp_utc": datetime.now(timezone.utc).isoformat(), "gateway": GATEWAY_URL,
              "transport": "real_http", "status": "unverified", "ui_status": "not_measured", "requests": []}
    headers = {}
    with httpx.Client(base_url=GATEWAY_URL, timeout=120, trust_env=False) as client:
        def call(method, path, **kwargs):
            response = client.request(method, path, headers=headers, **kwargs)
            report["requests"].append({"method": method, "path": path, "status": response.status_code})
            if response.status_code >= 400:
                raise RuntimeError(f"{method} {path}: HTTP {response.status_code}")
            return response.json()
        try:
            gateway = call("GET", "/health")
            if gateway.get("service") != "dusnx-gateway":
                raise RuntimeError("Port 8080 is not DUSN-X Gateway")
            health = call("GET", "/v1/health")
            report["runtime_mode"] = health.get("runtime_mode")
            report["model_version"] = health.get("model_version")
            if health.get("provider_ok") is not True:
                report["provider_health"] = {k: health.get("provider", {}).get(k)
                                             for k in ("available", "reachable", "configured_model", "error")}
                raise RuntimeError("Ollama unavailable according to Gateway /v1/health")
            credentials = {"username": f"acceptance_{secrets.token_hex(8)}", "password": secrets.token_urlsafe(24)}
            call("POST", "/v1/auth/register", json=credentials)
            token = call("POST", "/v1/auth/login", json=credentials)["token"]
            headers["Authorization"] = f"Bearer {token}"
            s1 = call("POST", "/v1/sessions", json={"title": "Acceptance setup"})["session_id"]
            def chat(sid, message):
                return call("POST", "/v1/chat", json={"session_id": sid, "message": message})
            chat(s1, REMEMBER)
            memories = call("GET", "/v1/memories?include_inactive=true")
            if len(memories) != 1 or "PostgreSQL" not in memories[0]["content"]:
                raise RuntimeError("Initial PostgreSQL memory missing")
            old_id = memories[0]["memory_id"]
            change = chat(s1, CHANGE)
            if (change.get("intent"), change.get("next_action")) != ("decision_modify_intent", "await_confirm"):
                raise RuntimeError("Change did not request confirmation")
            if chat(s1, CONFIRM).get("intent") != "decision_update":
                raise RuntimeError("Confirmation did not update decision")
            s2 = call("POST", "/v1/sessions", json={"title": "Acceptance recall"})["session_id"]
            if s1 == s2:
                raise RuntimeError("New session was not created")
            reply = chat(s2, QUERY)
            memories = call("GET", "/v1/memories?include_inactive=true")
            report["checks"] = check_final(reply, memories, old_id)
            report["final_response"] = {k: reply.get(k) for k in
                ("reply", "provider_ok", "provider_used", "provider_called", "response_source", "state_version", "model_used", "tokens_generated")
                if reply.get(k) is not None}
            generated = chat(call("POST", "/v1/sessions", json={"title": "Provider acceptance"})["session_id"],
                             "Viết hai câu về việc đọc sách.")
            report["checks"]["ollama_generation"] = (
                generated.get("provider_called") is True and generated.get("response_source") == "llm"
                and generated.get("provider_ok") is True and generated.get("provider_used") == "ollama"
                and bool(generated.get("model_used")))
            event = call("POST", "/v1/me/events", json={"platform": "powerpoint", "event_type": "slide_overview",
                        "content": "Slide trình bày kiến trúc: Cơ sở dữ liệu MongoDB", "feedback_value": 0.0})
            state = call("GET", "/v1/me/state")
            timeline = call("GET", "/v1/me/events")["events"]
            report["checks"]["cross_client_state"] = (
                event["state_version"] > reply["state_version"] and state["state_version"] == event["state_version"]
                and {"web", "powerpoint"}.issubset({e["platform"] for e in timeline}))
            report["status"] = "passed" if all(report["checks"].values()) else "unverified"
        except Exception as exc:
            # Never include request objects/headers or auth bodies.
            report["error"] = f"{type(exc).__name__}: {exc}" if not isinstance(exc, httpx.HTTPError) else type(exc).__name__
        finally:
            if headers:
                try:
                    call("POST", "/v1/auth/logout")
                except Exception:
                    report["logout"] = "failed"
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return report["status"] == "passed"


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", default="runtime/week2-http.json")
    args = parser.parse_args()
    sys.exit(0 if run_verification(args.output) else 1)
