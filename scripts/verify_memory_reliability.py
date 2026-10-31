"""Real local HTTP/Chromium checks on new synthetic databases, without LLM evaluation.

Reuses the native Week 4 process owner. Never opens SFT test or holdout files.
Run from the repository root with the venv Python and dotnet on PATH.
"""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import secrets
import shutil
import sqlite3

import httpx

from verify_week4_runtime import Stack, API


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", required=True, help="Must not already exist")
    parser.add_argument("--chromium", default="/usr/bin/chromium")
    args = parser.parse_args()
    out = Path(args.output_dir).resolve()
    out.mkdir(parents=True, exist_ok=False)
    report = {"timestamp_utc": datetime.now(timezone.utc).isoformat(),
              "transport": "real_local_http_gateway_fastapi_sqlite", "checks": {},
              "llm_generation_verified": False, "protected_test_read": False}
    checks = report["checks"]
    try:
        with Stack(out / "stack", DUSNX_OLLAMA_URL="http://127.0.0.1:9") as stack:
            a, b = API(stack.url), API(stack.url)
            try:
                health = a.call("GET", "/v1/health")
                report["runtime"] = {k: health[k] for k in ("runtime_mode", "checkpoint_loaded", "provider_ok")}
                uid = a.login_new(); b.login_new(); sid = a.session()
                project = a.call("POST", "/v1/projects", 201, json={"name": "Synthetic Alpha"})["project_id"]
                other = a.call("POST", "/v1/projects", 201, json={"name": "Synthetic Beta"})["project_id"]
                def memory(text, project_id):
                    return a.call("POST", "/v1/memories", 201, json={"info_type": "decision", "content": text, "project_id": project_id})
                old = memory("Chọn PostgreSQL cho cơ sở dữ liệu.", project)
                excluded = memory("Chọn MySQL cho cơ sở dữ liệu.", other)
                b.call("GET", f"/v1/memories/{old['memory_id']}", 404)
                latest = a.call("PUT", f"/v1/memories/{old['memory_id']}", json={"content": "Chọn MongoDB cho cơ sở dữ liệu."})
                def chat(text, **extra):
                    return a.call("POST", "/v1/chat", json={"session_id": sid, "message": text,
                                  "project_id": project, "request_id": secrets.token_hex(16), **extra})
                reply = chat("Cơ sở dữ liệu được chọn là gì?")
                assert "MongoDB" in reply["reply"] and "PostgreSQL" not in reply["reply"] and "MySQL" not in reply["reply"]
                assert reply["memory_ids_used"] == [latest["memory_id"]]
                assert excluded["memory_id"] not in reply["candidate_memory_ids"] and not reply["provider_called"]
                history = a.call("GET", f"/v1/memories/{latest['memory_id']}/history")
                assert [m["memory_id"] for m in history] == [old["memory_id"], latest["memory_id"]]
                checks["active_superseded_user_project_provenance_history"] = True
                proposed = chat("Đổi MongoDB sang SQLite")
                assert proposed["next_action"] == "await_confirm"
                confirmed = chat("Có")
                assert confirmed["intent"] == "decision_update"
                current = confirmed["memory_ids_used"][0]
                assert "SQLite" in chat("Cơ sở dữ liệu được chọn là gì?")["reply"]
                a.call("DELETE", f"/v1/memories/{current}", 204)
                missing = chat("Cơ sở dữ liệu được chọn là gì?")
                assert missing["next_action"] == "clarify" and not missing["memory_ids_used"]
                checks["confirmed_update_delete_and_missing_context"] = True
                memory("Chọn Penpot cho công cụ thiết kế.", project)
                memory("Chọn trà sen cho đồ uống buổi họp.", project)
                ambiguous = chat("Quyết định hiện tại của tôi là gì?")
                assert ambiguous["next_action"] == "clarify" and "?" in ambiguous["reply"]
                checks["ambiguity_clarifies"] = True
                # No inference model is installed; the real configured provider is unreachable.
                payload = {"session_id": sid, "message": "Viết hai câu về một buổi sáng yên tĩnh.", "request_id": secrets.token_hex(16)}
                failed = a.call("POST", "/v1/chat", json=payload)
                retried = a.call("POST", "/v1/chat", json={**payload, "is_retry": True})
                assert not failed["provider_ok"] and not retried["provider_ok"]
                assert failed["response_source"] == "provider_error"
                messages = a.call("GET", f"/v1/sessions/{sid}/messages")
                assert sum(m["role"] == "user" and m["content"] == payload["message"] for m in messages) == 1
                assert not any(m["role"] == "assistant" and m["content"] == failed["reply"] for m in messages)
                checks["provider_offline_retry_no_duplicate_no_error_as_answer"] = True
                with httpx.Client(base_url=stack.url, trust_env=False) as c:
                    assert c.post("/v1/chat", content="invalid", headers={"Content-Type": "text/plain"}).status_code == 415
                    assert c.post("/v1/chat", content=b"x" * 1048577, headers={"Content-Type": "application/json", "Connection": "close"}).status_code == 413
                    assert c.post("/api/v1/events", headers={"Origin": "https://untrusted.invalid"}, json={}).status_code == 404
                    assert c.get("/api/v1/state/web/synthetic", headers={"Origin": "https://untrusted.invalid"}).status_code == 404
                    assert c.post("/webhooks/zalo", json={"eventId": "synthetic", "userId": "synthetic", "message": "probe"}).status_code == 503
                checks["request_limits_legacy_origin_webhook_fail_closed"] = True
                database = stack.directory / "ai" / "memory.db"
                # Fault injection is confined to this disposable database.
                with sqlite3.connect(database) as conn:
                    conn.execute("CREATE TRIGGER synthetic_write_failure BEFORE INSERT ON memories BEGIN SELECT RAISE(ABORT,'synthetic write failure'); END")
                response = a.client.post("/v1/memories", headers=a.headers,
                                         json={"info_type": "decision", "content": "Synthetic failure must not be saved"})
                assert response.status_code == 503
                assert response.json()["detail"] == "Database temporarily unavailable. Check state before retrying a write."
                with sqlite3.connect(database) as conn:
                    assert conn.execute("SELECT COUNT(*) FROM memories WHERE content=?", ("Synthetic failure must not be saved",)).fetchone()[0] == 0
                    conn.execute("DROP TRIGGER synthetic_write_failure")
                memory("Synthetic write recovery fact", project)
                checks["sqlite_write_failure_not_success"] = True
                # Per-DB SQLite API backup, then restore to a new directory; never replace originals.
                backup = out / "backup"; backup.mkdir()
                for name in ("auth.db", "memory.db"):
                    with sqlite3.connect(f"file:{(stack.directory / 'ai' / name).as_posix()}?mode=ro", uri=True) as src:
                        with sqlite3.connect(backup / name) as dst:
                            src.backup(dst)
                            assert dst.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
                self_browser(stack.url, args.chromium, checks)
            finally:
                try:
                    a.close()
                finally:
                    b.close()
        restored = Stack(out / "restored", DUSNX_OLLAMA_URL="http://127.0.0.1:9")
        (restored.directory / "ai").mkdir()
        for name in ("auth.db", "memory.db"):
            shutil.copy2(backup / name, restored.directory / "ai" / name)
        with restored:
            with sqlite3.connect(restored.directory / "ai" / "memory.db") as conn:
                assert conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
            with httpx.Client(base_url=restored.url, trust_env=False) as c:
                assert c.get("/v1/health").json()["service"] == "dusnx-ai-api"
                assert c.get("/v1/auth/me", headers=a.headers).json()["user_id"] == uid
                restored_memories = c.get("/v1/memories", headers=a.headers).json()
                assert any("Penpot" in m["content"] for m in restored_memories)
        checks["sqlite_backup_restore_new_directory_startup"] = True
        corrupt = out / "invalid-checkpoint.pt"; corrupt.write_bytes(b"synthetic invalid checkpoint")
        with Stack(out / "checkpoint-fault", DUSNX_CHECKPOINT=str(corrupt), DUSNX_OLLAMA_URL="http://127.0.0.1:9") as fault:
            with httpx.Client(base_url=fault.url, trust_env=False) as c:
                h = c.get("/v1/health").json()
                assert h["runtime_mode"] == "bootstrap_rules" and not h["checkpoint_loaded"]
                assert "Checkpoint loading failed" in h["metadata"]["warning"]
        checks["invalid_checkpoint_honest_fallback"] = True
        broken_db = out / "broken-db"; broken_db.mkdir(); (broken_db / "memory.db").write_bytes(b"not sqlite")
        try:
            with Stack(out / "database-fault", DUSNX_DATA_DIR=str(broken_db)):
                raise AssertionError("Corrupt SQLite must not start successfully")
        except RuntimeError:
            assert "file is not a database" in (out / "database-fault" / "ai.log").read_text()
            checks["corrupt_database_startup_refused"] = True
        report["status"] = "passed"
    except Exception as exc:
        report["status"] = "failed"; report["failure_type"] = type(exc).__name__
        raise
    finally:
        (out / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
        print(json.dumps({"status": report.get("status"), "checks": checks}, ensure_ascii=False))


def self_browser(url, executable, checks):
    from playwright.sync_api import sync_playwright, expect
    with sync_playwright() as pw:
        browser = pw.chromium.launch(executable_path=executable, headless=True, args=["--no-sandbox"])
        try:
            page = browser.new_page()
            page.goto(url)
            page.locator("#tabRegister").click()
            page.locator("#regUsername").fill("roadmap_ui_" + secrets.token_hex(6))
            page.locator("#regPassword").fill(secrets.token_urlsafe(24))
            page.locator("#registerBtn").click()
            expect(page.locator("#messageInput")).to_be_visible()
            def send(text):
                page.locator("#messageInput").fill(text)
                with page.expect_response(lambda r: r.url.endswith("/v1/chat")) as response:
                    page.locator("#sendBtn").click()
                expect(page.locator("#sendBtn")).to_be_enabled()
                return response.value.json()
            saved = send("Hãy nhớ rằng chúng tôi chọn Penpot cho công cụ thiết kế.")
            assert saved["memory_ids_used"] and not saved["provider_called"]
            assert send("Công cụ thiết kế được chọn là gì?")["response_source"] == "grounded_template"
            failed = send("Viết một đoạn văn về đại dương.")
            assert failed["provider_ok"] is False
            expect(page.locator(".system-error").last).to_be_visible()
            page.route("**/v1/chat", lambda route: route.abort())
            page.locator("#messageInput").fill("Synthetic network interruption")
            page.locator("#sendBtn").click()
            expect(page.locator(".system-error")).to_have_count(2)
            checks["chromium_register_login_memory_provenance_provider_error_network_error"] = True
        finally:
            browser.close()


if __name__ == "__main__":
    main()
