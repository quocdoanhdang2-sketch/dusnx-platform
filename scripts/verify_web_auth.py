"""Verify Web auth visibility and delayed responses through real local services.

Accounts and databases are synthetic. Delays are injected by Chromium routing;
login/logout requests still reach the real Gateway/FastAPI authentication code.
"""
import argparse
import json
import secrets
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
    report = {"timestamp_utc": datetime.now(UTC).isoformat(), "status": "failed",
              "transport": "real_gateway_fastapi_chromium_with_controlled_delays", "checks": {}}
    try:
        with Stack(out / "stack", DUSNX_OLLAMA_URL="http://127.0.0.1:9") as stack:
            api = API(stack.url)
            try:
                credentials = {"username": "auth_ui_" + secrets.token_hex(8),
                               "password": secrets.token_urlsafe(24)}
                uid = api.call("POST", "/v1/auth/register", 201, json=credentials)["user_id"]
                with sync_playwright() as pw:
                    browser = pw.chromium.launch(executable_path=args.chromium, headless=True)
                    try:
                        page = browser.new_page()
                        page.goto(stack.url)
                        expect(page.locator("#loginForm")).to_be_visible()
                        expect(page.locator("#registerForm")).to_be_hidden()
                        page.locator("#tabRegister").click()
                        expect(page.locator("#registerForm")).to_be_visible()
                        expect(page.locator("#loginForm")).to_be_hidden()
                        page.locator("#tabLogin").click()
                        report["checks"]["only_selected_auth_form_visible"] = True

                        page.locator("#loginUsername").fill(credentials["username"])
                        page.locator("#loginPassword").fill(credentials["password"])
                        held = []
                        page.route("**/v1/auth/login", lambda route: held.append(route))
                        with page.expect_request("**/v1/auth/login"):
                            page.locator("#loginBtn").click()
                        page.evaluate("() => undefined")
                        route = held.pop()
                        response = route.fetch()
                        assert response.status == 200
                        page.evaluate("() => handleLogout()")
                        # Revoke the real token that the UI deliberately discards.
                        api.client.post("/v1/auth/logout", headers={
                            "Authorization": "Bearer " + response.json()["token"]})
                        route.fulfill(response=response)
                        expect(page.locator("#loginBtn")).to_be_enabled()
                        assert page.evaluate("() => authToken === null && currentUser === null")
                        expect(page.locator("#authScreen")).to_be_visible()
                        report["checks"]["late_real_login_cannot_restore_logged_out_session"] = True
                        page.unroute("**/v1/auth/login")

                        def login():
                            page.locator("#loginBtn").click()
                            page.wait_for_function("() => currentSessionId !== null && !isCreatingSession")
                            assert page.evaluate("() => currentUser.user_id") == uid
                        login()
                        report["checks"]["real_login_after_discarded_response"] = True

                        # Do not let a slow revoke response keep local data visible,
                        # or clear the next successful login when it finally returns.
                        held_logout = []
                        page.route("**/v1/auth/logout", lambda route: held_logout.append(route))
                        with page.expect_request("**/v1/auth/logout"):
                            page.evaluate("() => { window.logoutPending = handleLogout(); }")
                        assert page.evaluate("() => authToken === null && currentSessionId === null")
                        expect(page.locator("#messageList")).to_be_empty()
                        expect(page.locator("#sessionList")).to_be_empty()
                        expect(page.locator("#authScreen")).to_be_visible()
                        report["checks"]["logout_clears_local_data_before_network_finishes"] = True
                        login()
                        route = held_logout.pop()
                        route.fulfill(response=route.fetch())
                        page.evaluate("() => window.logoutPending")
                        assert page.evaluate("() => authToken !== null && currentUser.user_id") == uid
                        expect(page.locator("#appScreen")).to_be_visible()
                        report["checks"]["old_logout_response_preserves_new_login"] = True
                        page.unroute("**/v1/auth/logout")
                        page.screenshot(path=str(out / "auth.png"))
                        page.evaluate("() => handleLogout()")
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
