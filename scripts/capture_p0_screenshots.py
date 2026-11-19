"""Capture high-resolution screenshots of the verified Club IT Assistant P0 demo.

Target URL: http://127.0.0.1:8090
Artifact output: C:/Users/Admin/.gemini/antigravity/brain/6b142ef1-30dd-4d89-878d-1711491e6b4c/screenshots
"""
from __future__ import annotations

import os
import sys
import time
from pathlib import Path
from playwright.sync_api import sync_playwright

OUT_DIR = Path(r"C:\Users\Admin\.gemini\antigravity\brain\6b142ef1-30dd-4d89-878d-1711491e6b4c\screenshots")
OUT_DIR.mkdir(parents=True, exist_ok=True)
CHROME_PATH = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
URL = "http://127.0.0.1:8090"


def capture_all():
    print(f"Launching Playwright against {URL}...")
    with sync_playwright() as p:
        browser = p.chromium.launch(executable_path=CHROME_PATH, headless=True)
        context = browser.new_context(viewport={"width": 1280, "height": 850})
        page = context.new_page()

        # 1. Login view with role quick buttons
        print("1. Capturing Login screen with 4-tier role buttons...")
        page.goto(URL)
        page.wait_for_selector("#loginUsername")
        time.sleep(1)
        shot1 = OUT_DIR / "01_login_roles.png"
        page.screenshot(path=str(shot1))
        print(f"   Saved {shot1.name}")

        # 2. 1-click Quick Login as Chủ nhiệm CLB (chunhiem / owner)
        print("2. Performing 1-click Quick Login as Chủ nhiệm CLB...")
        page.locator("button.btn-role-quick:has-text('Chủ nhiệm CLB')").click()
        page.wait_for_selector("#viewChat", state="visible", timeout=10000)
        time.sleep(2)

        # 3. Ask Question 1: Lab room rules (Quy định sử dụng phòng lab)
        print("3. Asking Q1: Quy định sử dụng phòng lab của CLB là gì?...")
        msg_input = page.locator("#messageInput")
        msg_input.fill("Quy định sử dụng phòng lab của CLB là gì?")
        page.locator("#sendBtn").click()
        # Wait for assistant response with doc 06
        page.wait_for_selector(".message.assistant", timeout=30000)
        time.sleep(2)
        shot2 = OUT_DIR / "02_lab_rules_doc06.png"
        page.screenshot(path=str(shot2))
        print(f"   Saved {shot2.name}")

        # 4. Ask Question 2: Fund deadline & recipient (Đóng quỹ)
        print("4. Asking Q2: Đóng quỹ trước ngày mấy và nộp cho ai?...")
        msg_input.fill("Đóng quỹ trước ngày mấy và nộp cho ai?")
        page.locator("#sendBtn").click()
        time.sleep(3)
        shot3 = OUT_DIR / "03_fund_deadline_doc16.png"
        page.screenshot(path=str(shot3))
        print(f"   Saved {shot3.name}")

        # 5. Ask Question 4 & 5: IT CodeFest location & Member criteria
        print("5. Asking Q4: IT CodeFest 2026 tổ chức ở đâu?...")
        msg_input.fill("IT CodeFest 2026 tổ chức ở đâu?")
        page.locator("#sendBtn").click()
        time.sleep(3)
        shot4 = OUT_DIR / "04_codefest_location_doc04.png"
        page.screenshot(path=str(shot4))
        print(f"   Saved {shot4.name}")

        # 6. Ask Question 6: Out of scope refusal (Giá vàng hôm nay bao nhiêu một chỉ?)
        print("6. Asking Q6: Giá vàng hôm nay bao nhiêu một chỉ?...")
        msg_input.fill("Giá vàng hôm nay bao nhiêu một chỉ?")
        page.locator("#sendBtn").click()
        time.sleep(2)
        shot5 = OUT_DIR / "05_out_of_scope_refusal.png"
        page.screenshot(path=str(shot5))
        print(f"   Saved {shot5.name}")

        # 7. Ask Question with 'So sánh với API' (Gemini comparison)
        print("7. Asking query with 'So sánh với API' enabled...")
        # Toggle checkbox via JS
        page.evaluate("() => { const cb = document.getElementById('compareWithApiToggle'); if (cb) { cb.checked = true; cb.dispatchEvent(new Event('change')); } }")
        msg_input.fill("Hãy viết lời chào mừng ngắn gọn gửi các bạn tân thành viên gia nhập CLB IT")
        page.locator("#sendBtn").click()
        # Wait for API comparison card
        print("   Waiting for Gemini comparison card...", flush=True)
        page.wait_for_selector(".api-comparison-card", timeout=60000)
        # Open details so card content is visible in screenshot
        page.evaluate("() => { const el = document.querySelector('.api-comparison-card'); if (el) el.open = true; }")
        time.sleep(2)
        shot6 = OUT_DIR / "06_gemini_api_comparison.png"
        page.screenshot(path=str(shot6))
        print(f"   Saved {shot6.name}")

        # Reset compare toggle
        page.evaluate("() => { const cb = document.getElementById('compareWithApiToggle'); if (cb) cb.checked = false; }")

        # 8. Document Library view (26 docs)
        print("8. Navigating to Kho tài liệu (26 documents)...")
        page.locator("#navDocuments").click()
        page.wait_for_selector("#viewDocuments")
        time.sleep(2)
        shot7 = OUT_DIR / "07_documents_library_26docs.png"
        page.screenshot(path=str(shot7))
        print(f"   Saved {shot7.name}")

        browser.close()
        print("All screenshots captured successfully!")


if __name__ == "__main__":
    capture_all()
