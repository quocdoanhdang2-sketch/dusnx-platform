"""Chromium against the real Gateway: buttons, history, XSS, mobile and lost-response retry."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import secrets
import sys

from playwright.sync_api import sync_playwright, expect


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--gateway", default="http://127.0.0.1:8080")
    p.add_argument("--output-dir", required=True)
    args = p.parse_args()
    out = Path(args.output_dir)
    out.mkdir(parents=True, exist_ok=False)
    report = dict(timestamp_utc=datetime.now(timezone.utc).isoformat(), transport="real_chromium_gateway_ollama",
                  status="unverified", checks={})
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        try:
            context = browser.new_context(viewport={"width": 1280, "height": 900})
            page = context.new_page()
            page.set_default_timeout(30000)
            page.goto(args.gateway)
            username, password = "w4_ui_" + secrets.token_hex(8), secrets.token_urlsafe(24)
            page.locator("#tabRegister").click()
            page.locator("#regUsername").fill(username)
            page.locator("#regPassword").fill(password)
            with page.expect_response(lambda r: r.url.endswith("/v1/sessions") and r.request.method == "POST"):
                page.locator("#registerBtn").click()
            expect(page.locator("#messageInput")).to_be_visible()
            def chat(text):
                page.locator("#messageInput").fill(text)
                with page.expect_response(lambda r: r.url.endswith("/v1/chat"), timeout=120000) as result:
                    page.locator("#sendBtn").click()
                data = result.value.json()
                expect(page.locator("#sendBtn")).to_be_enabled()
                expect(page.locator("#statusIndicator")).to_be_hidden()
                return data
            first = chat("Hãy nhớ rằng chúng tôi chọn PostgreSQL cho cơ sở dữ liệu.")
            assert first["intent"] == "memory_create"
            chat("Đổi PostgreSQL sang MongoDB")
            expect(page.locator("#pendingDecisionBanner")).to_be_visible()
            page.locator("#pendingDecisionBanner").screenshot(path=str(out / "pending.png"))
            with page.expect_response(lambda r: "/resolve" in r.url and r.request.method == "POST"):
                page.locator("#pendingDecisionBanner button").nth(1).click()
            expect(page.locator("#pendingDecisionBanner")).to_be_hidden()
            chat("Đổi PostgreSQL sang MongoDB")
            with page.expect_response(lambda r: "/resolve" in r.url and r.request.method == "POST"):
                page.locator("#pendingDecisionBanner button").nth(0).click()
            expect(page.locator("#pendingDecisionBanner")).to_be_hidden()
            # Exercise additional click after resolution; stale isResolving used to block this.
            recalled = chat("Cơ sở dữ liệu được chọn là gì?")
            assert "MongoDB" in recalled["reply"] and "PostgreSQL" not in recalled["reply"]
            assert not recalled["provider_called"] and recalled["response_source"] == "grounded_template"
            report["checks"]["confirmation_and_cancel_buttons"] = True
            s1 = page.evaluate("currentSessionId")
            with page.expect_response(lambda r: r.url.endswith("/v1/sessions") and r.request.method == "POST"):
                page.locator("#newChatBtn").click()
            expect(page.locator("#chatTitle")).to_have_text("Phiên chat mới")
            recalled = chat("Cơ sở dữ liệu được chọn là gì?")
            assert recalled["session_id"] != s1 and "MongoDB" in recalled["reply"]
            page.locator(f'[data-session-id="{s1}"]').click()
            expect(page.locator("#messageList")).to_contain_text("PostgreSQL")
            expect(page.locator("#messageList")).to_contain_text("MongoDB")
            report["checks"]["session_selection_and_history"] = True
            # Inject a transport loss AFTER the real server completed its mutation.
            lost = []
            def lose_response(route):
                response = route.fetch()
                assert response.status == 200
                lost.append(response.json())
                route.abort("connectionreset")
            page.route("**/v1/chat", lose_response, times=1)
            draft = "Hãy nhớ rằng tôi thích trà sen trong cuộc họp."
            page.locator("#messageInput").fill(draft)
            page.locator("#sendBtn").click()
            expect(page.locator("#errorBanner")).to_be_visible()
            expect(page.locator("#messageInput")).to_have_value(draft)
            assert len(lost) == 1 and lost[0]["intent"] == "memory_create"
            page.locator("#viewChat").screenshot(path=str(out / "network-retry.png"))
            # A later successful request must not replace the failed card's ID.
            chat("Hãy nhớ rằng giờ họp của nhóm là chín giờ.")
            with page.expect_response(lambda r: r.url.endswith("/v1/chat")) as retry:
                page.locator(".system-error button").last.click()
            replay = retry.value.json()
            assert replay["message_id"] == lost[0]["message_id"] and replay["reply"] == lost[0]["reply"]
            assert replay["replayed"] and replay["response_source"] == "replay" and not replay["provider_called"]
            expect(page.locator("#sendBtn")).to_be_enabled()
            # Read only this synthetic user's memories via the actual authenticated Gateway.
            token = page.evaluate("authToken")
            memories = context.request.get(args.gateway + "/v1/memories", headers={"Authorization": "Bearer " + token}).json()
            assert len([m for m in memories if "trà sen" in m["content"]]) == 1
            report["checks"]["lost_success_response_retry_no_duplicate"] = True
            report["checks"]["later_success_preserves_failed_request_id"] = True
            # Real mutation containing untrusted HTML; assert plain text, no HTML execution.
            payload = '<img src=x onerror="window.__dusnx_xss=1"><script>window.__dusnx_xss=2</script>'
            chat("Hãy nhớ rằng ghi chú thử an toàn là " + payload)
            expect(page.locator("#messageList")).to_contain_text(payload)
            assert page.locator("#messageList img, #messageList script").count() == 0
            assert page.evaluate("window.__dusnx_xss || 0") == 0
            page.locator("#navMemory").click()
            expect(page.locator("#memoryList")).to_contain_text(payload)
            assert page.locator("#memoryList img, #memoryList script").count() == 0
            page.locator("#viewMemory").screenshot(path=str(out / "xss-memory.png"))
            report["checks"]["RT-13"] = True
            page.evaluate("showView('chat')")
            generated = chat("Viết một câu ngắn về lợi ích đọc sách.")
            assert generated["provider_ok"] and generated["provider_called"] and generated["response_source"] == "llm"
            assert generated["model_used"] == "qwen2.5:0.5b"
            report["checks"]["RT-01"] = True
            report["generation"] = {k: generated[k] for k in ("reply", "provider_called", "provider_used", "model_used", "response_source")}
            page.set_viewport_size({"width": 390, "height": 844})
            page.wait_for_function("document.getElementById('sidebar').getBoundingClientRect().right <= 0")
            expect(page.locator("#messageInput")).to_be_visible()
            assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
            page.locator("#viewChat").screenshot(path=str(out / "mobile.png"))
            report["checks"]["responsive_390px"] = True
            page.set_viewport_size({"width": 1280, "height": 900})
            # Revoke the synthetic token at server, then trigger Web's real 401 flow.
            context.request.post(args.gateway + "/v1/auth/logout", headers={"Authorization": "Bearer " + token})
            page.locator("#messageInput").fill("Nội dung chưa gửi cần giữ lại")
            page.locator("#sendBtn").click()
            expect(page.locator("#authScreen")).to_have_class("screen active")
            expect(page.locator("#loginError")).to_contain_text("hết hạn")
            assert page.evaluate("authToken") is None
            assert page.evaluate("sessionStorage.getItem('dusnx_token')") is None
            expect(page.locator("#messageInput")).to_have_value("Nội dung chưa gửi cần giữ lại")
            report["checks"]["web_401_clears_token_preserves_draft"] = True
            report["status"] = "passed"
        except Exception as exc:
            report["error"] = type(exc).__name__ + ": " + str(exc)
        finally:
            browser.close()
    (out / "browser.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.exit(main())
