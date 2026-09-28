"""Optional Playwright acceptance on the actual Web UI served by Gateway."""
from datetime import datetime, timezone
import argparse
import json
from pathlib import Path
import secrets
import sys

from verify_real_ollama_week2 import GATEWAY_URL, REMEMBER, CHANGE, CONFIRM, QUERY, check_final


def main():
    from playwright.sync_api import sync_playwright, expect
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--browser-executable", help="Optional installed Chromium/Chrome executable")
    parser.add_argument("--output-dir", default="runtime/week2-ui")
    args = parser.parse_args()
    output = Path(args.output_dir)
    output.mkdir(parents=True, exist_ok=True)
    report = dict(timestamp_utc=datetime.now(timezone.utc).isoformat(), status="unverified",
                  transport="browser_ui", gateway=GATEWAY_URL, requests=[])
    with sync_playwright() as pw:
        browser = None
        try:
            browser = pw.chromium.launch(headless=True, executable_path=args.browser_executable)
            context = browser.new_context(viewport={"width": 1280, "height": 900})
            page = context.new_page()
            page.set_default_timeout(120000)

            def observe(response):
                if response.url.startswith(GATEWAY_URL + "/v1/"):
                    # No headers, auth bodies, session IDs or query parameters saved.
                    from urllib.parse import urlsplit
                    path = urlsplit(response.url).path
                    if path.startswith("/v1/sessions/"):
                        path = "/v1/sessions/<id>/messages"
                    report["requests"].append(dict(method=response.request.method, path=path, status=response.status))
            page.on("response", observe)
            page.goto(GATEWAY_URL)
            credentials = (f"ui_{secrets.token_hex(8)}", secrets.token_urlsafe(24))
            page.locator("#tabRegister").click()
            page.locator("#regUsername").fill(credentials[0])
            page.locator("#regPassword").fill(credentials[1])
            with page.expect_response(lambda r: r.url.endswith("/v1/sessions") and r.request.method == "POST"):
                page.locator("#registerBtn").click()
            # Exercise the explicit login form as well as registration auto-login.
            page.locator(".logout-btn").click()
            page.locator("#tabLogin").click()
            page.locator("#loginUsername").fill(credentials[0])
            page.locator("#loginPassword").fill(credentials[1])
            with page.expect_response(lambda r: r.url.endswith("/v1/sessions") and r.request.method == "POST"):
                page.locator("#loginBtn").click()

            def chat(message):
                page.locator("#messageInput").fill(message)
                with page.expect_response(lambda r: r.url.endswith("/v1/chat") and r.request.method == "POST") as response:
                    page.locator("#sendBtn").click()
                data = response.value.json()
                expect(page.locator("#sendBtn")).to_be_enabled()
                expect(page.locator("#statusIndicator")).to_be_hidden()
                expect(page.locator("#messageList")).to_contain_text(data["reply"])
                return data

            remembered = chat(REMEMBER)
            old_id = remembered["memory_ids_used"][0]
            change = chat(CHANGE)
            assert change["next_action"] == "await_confirm", "UI change did not request confirmation"
            confirmed = chat(CONFIRM)
            assert confirmed["intent"] == "decision_update", "UI confirmation did not update"
            with page.expect_response(lambda r: r.url.endswith("/v1/sessions") and r.request.method == "POST"):
                page.locator("#newChatBtn").click()
            reply = chat(QUERY)
            expect(page.locator("#providerStatus")).to_contain_text("sẵn sàng")
            expect(page.locator("#modelStatus")).to_contain_text("Trained")
            assert reply["session_id"] != remembered["session_id"], "UI did not switch session"
            page.locator("#viewChat").screenshot(path=str(output / "chat.png"))
            page.locator("#navMemory").click()
            with page.expect_response(lambda r: "/v1/memories?" in r.url and "include_inactive=true" in r.url) as response:
                page.locator("#showInactive").check()
            memories = response.value.json()
            expect(page.locator("#memoryList .card.inactive")).to_contain_text("PostgreSQL")
            expect(page.locator("#memoryList .card:not(.inactive)")).to_contain_text("MongoDB")
            page.locator("#viewMemory").screenshot(path=str(output / "memory.png"))
            report["checks"] = check_final(reply, memories, old_id)
            report["checks"]["ui_rendered_reply_and_memory"] = True
            report["final_response"] = {k: reply[k] for k in ("reply", "provider_ok", "provider_used")}
            report["status"] = "passed" if all(report["checks"].values()) else "unverified"
            page.locator(".logout-btn").click()
        except Exception as exc:
            report["error"] = f"{type(exc).__name__}: {exc}"
        finally:
            if browser:
                browser.close()
    (output / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    sys.exit(main())
