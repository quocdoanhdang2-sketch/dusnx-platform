"""Real Gateway/FastAPI/Chromium history regression on a new synthetic database.

Run from the repository root with the venv Python and dotnet on PATH.
Does not call generation or open protected benchmark/training data.
"""
import argparse
import json
import secrets
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

from playwright.sync_api import expect, sync_playwright
from verify_week4_runtime import API, Stack


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--chromium", default="/usr/bin/chromium")
    args = parser.parse_args()
    out = Path(args.output_dir).resolve()
    out.mkdir(parents=True, exist_ok=False)
    report = {"timestamp_utc": datetime.now(UTC).isoformat(), "checks": {},
              "transport": "real_gateway_fastapi_sqlite_chromium", "status": "failed"}
    try:
        with Stack(out / "stack", DUSNX_OLLAMA_URL="http://127.0.0.1:9") as stack:
            api = API(stack.url)
            try:
                uid = api.login_new()
                sid, other = api.session(), api.session()
                with sqlite3.connect(stack.directory / "ai" / "memory.db") as conn:
                    for session_id, contents in ((sid, [f"history-{i}" for i in range(205)]),
                                                 (other, ["other-session"])):
                        conn.executemany(
                            "INSERT INTO chat_messages(message_id,session_id,user_id,role,content,"
                            "memory_ids_used,created_at) VALUES(?,?,?,?,?,?,?)",
                            [(secrets.token_hex(16), session_id, uid, "user", text, "[]",
                              "2026-11-02T00:00:00+00:00") for text in contents],
                        )
                health = api.call("GET", "/v1/health")
                assert health["checkpoint_loaded"] and health["runtime_mode"] == "trained_dusnx"
                report["checks"]["uploaded_router_loaded"] = True
                with sync_playwright() as pw:
                    browser = pw.chromium.launch(executable_path=args.chromium, headless=True)
                    try:
                        page = browser.new_page()
                        # Synthetic token stays in process memory, never in reports.
                        token = api.headers["Authorization"].removeprefix("Bearer ")
                        page.add_init_script("sessionStorage.setItem('dusnx_token', " + json.dumps(token) + ")")
                        page.goto(stack.url)
                        page.wait_for_function("() => currentSessionId !== null && !isCreatingSession")
                        page.evaluate("sid => openSession(sid, 'Long conversation')", sid)
                        bubbles = page.locator("#messageList .bubble")
                        expect(bubbles).to_have_count(100)
                        assert bubbles.all_text_contents() == [f"history-{i}" for i in range(105, 205)]
                        button = page.locator("#olderMessagesBtn")
                        button.click()
                        expect(bubbles).to_have_count(200)
                        button.click()
                        expect(bubbles).to_have_count(205)
                        expect(button).to_be_hidden()
                        assert bubbles.all_text_contents() == [f"history-{i}" for i in range(205)]
                        report["checks"]["latest_100_then_all_205_in_order"] = True

                        # Hold a real history request while navigating to another session.
                        held = []
                        pattern = f"**/v1/sessions/{sid}/messages/page"
                        page.route(pattern, lambda route: held.append(route))
                        with page.expect_request(pattern):
                            page.evaluate("sid => { window.historyPending = openSession(sid, 'Delayed'); }", sid)
                        page.evaluate("sid => openSession(sid, 'Other conversation')", other)
                        expect(bubbles).to_have_text(["other-session"])
                        held.pop().fulfill(json={"messages": [{"role": "user", "content": "stale-history"}],
                                                "next_before": None})
                        page.evaluate("window.historyPending")
                        expect(bubbles).to_have_text(["other-session"])
                        report["checks"]["delayed_history_does_not_cross_sessions"] = True
                        page.unroute(pattern)

                        page.evaluate("sid => openSession(sid, 'Long conversation')", sid)
                        older_held = []
                        page.route(pattern + "?**", lambda route: older_held.append(route))
                        with page.expect_request(pattern + "?**"):
                            page.evaluate("() => { window.olderPending = loadOlderMessages(); }")
                        page.evaluate("sid => openSession(sid, 'Other conversation')", other)
                        older_held.pop().fulfill(json={"messages": [{"role": "user", "content": "stale-older"}],
                                                      "next_before": None})
                        # Wait for the deferred loader to finish, rather than a fixed sleep.
                        page.evaluate("() => window.olderPending")
                        expect(bubbles).to_have_text(["other-session"])
                        page.unroute(pattern + "?**")
                        page.evaluate("sid => openSession(sid, 'Long conversation')", sid)
                        expect(button).to_be_enabled()
                        button.click()
                        expect(bubbles).to_have_count(200)
                        report["checks"]["older_request_switch_and_button_reset"] = True

                        page.evaluate("sid => openSession(sid, 'Long conversation')", sid)
                        page.route(pattern + "?**", lambda route: route.fulfill(
                            status=503, json={"detail": "Synthetic history outage"}))
                        button.click()
                        expect(page.locator("#errorBanner")).to_contain_text("Synthetic history outage")
                        expect(bubbles).to_have_count(100)
                        expect(button).to_be_enabled()
                        page.unroute(pattern + "?**")
                        button.click()
                        expect(bubbles).to_have_count(200)
                        assert bubbles.all_text_contents() == [f"history-{i}" for i in range(5, 205)]
                        report["checks"]["failed_page_retries_without_lost_or_duplicate_messages"] = True
                        page.screenshot(path=str(out / "history.png"))

                        page.route(pattern, lambda route: held.append(route))
                        with page.expect_request(pattern):
                            page.evaluate("sid => { window.historyPending = openSession(sid, 'Delayed'); }", sid)
                        page.evaluate("() => handleLogout()")
                        api.headers = {}  # The browser revoked this same synthetic token.
                        held.pop().fulfill(json={"messages": [{"role": "user", "content": "after-logout"}],
                                                "next_before": None})
                        page.evaluate("() => window.historyPending")
                        expect(page.locator("#authScreen")).to_be_visible()
                        expect(bubbles).to_have_count(0)
                        report["checks"]["logout_discards_inflight_history"] = True
                    finally:
                        browser.close()
            finally:
                api.close()
        report["status"] = "passed"
    finally:
        (out / "report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(report))


if __name__ == "__main__":
    main()
