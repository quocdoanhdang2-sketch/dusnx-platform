"""Automated browser demo and screenshot capture for CLB IT Assistant.

Uses Playwright with local Chrome to navigate through the web interface,
execute real interactions, and capture high-resolution screenshots of all views.
"""
import os
import sys
import time
from pathlib import Path
from playwright.sync_api import sync_playwright

OUT_DIR = Path(r"C:\Users\Admin\.gemini\antigravity\brain\bb210f0e-f8f1-4f0f-b952-ef61d4b856ed\demo_screenshots")
OUT_DIR.mkdir(parents=True, exist_ok=True)
CHROME_PATH = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
URL = "http://127.0.0.1:8080"


def run_demo():
    print(f"Starting automated demo on {URL}...")
    with sync_playwright() as p:
        browser = p.chromium.launch(executable_path=CHROME_PATH, headless=True)
        context = browser.new_context(viewport={"width": 1280, "height": 850})
        page = context.new_page()

        # Step 1: Login Screen with 4-Tier Role Buttons
        print("1. Capturing Login view...")
        page.goto(URL)
        page.wait_for_selector("#loginUsername")
        time.sleep(1)
        shot1 = OUT_DIR / "01_login_roles.png"
        page.screenshot(path=str(shot1), full_page=False)
        print(f"   Saved {shot1.name}")

        # Step 2: Quick Login as 'chunhiem' (Owner)
        print("2. Performing 1-click Quick Login as Chủ nhiệm CLB...")
        page.locator("button.btn-role-quick:has-text('Chủ nhiệm CLB')").click()

        # Wait for Chat view and announcements
        page.wait_for_selector("#viewChat", state="visible", timeout=10000)
        time.sleep(2)
        shot2 = OUT_DIR / "02_chat_initial.png"
        page.screenshot(path=str(shot2), full_page=False)
        print(f"   Saved {shot2.name}")

        # Step 3: Ask a question in Chat AI
        print("3. Asking Club question: 'CLB mình có những ban chuyên môn nào và lịch sinh hoạt ra sao?'...", flush=True)
        message_input = page.locator("#messageInput")
        message_input.fill("CLB mình có những ban chuyên môn nào và lịch sinh hoạt ra sao?")
        time.sleep(0.5)
        page.locator("#sendBtn").click()

        # Wait for assistant response to render
        print("   Waiting for Assistant response and RAG citations...", flush=True)
        page.wait_for_selector(".message.assistant", timeout=20000)
        time.sleep(3)
        shot3 = OUT_DIR / "03_chat_rag_response.png"
        page.screenshot(path=str(shot3), full_page=False)
        print(f"   Saved {shot3.name}", flush=True)

        # Step 4: Documents View
        print("4. Navigating to Kho tài liệu (18 documents)...")
        page.locator("#navDocuments").click()
        page.wait_for_selector("#viewDocuments")
        time.sleep(2)
        shot4 = OUT_DIR / "04_documents_corpus.png"
        page.screenshot(path=str(shot4), full_page=False)
        print(f"   Saved {shot4.name}")

        # Step 5: Personal Notebook View
        print("5. Navigating to Sổ tay cá nhân...")
        page.locator("#navMemory").click()
        page.wait_for_selector("#viewMemory")
        time.sleep(1.5)
        shot5 = OUT_DIR / "05_personal_notebook.png"
        page.screenshot(path=str(shot5), full_page=False)
        print(f"   Saved {shot5.name}")

        # Step 6: Management View (Members)
        print("6. Navigating to Quản lý CLB (Members)...")
        page.locator("#navManagement").click()
        page.wait_for_selector("#viewManagement")
        time.sleep(1.5)
        shot6 = OUT_DIR / "06_mgmt_members.png"
        page.screenshot(path=str(shot6), full_page=False)
        print(f"   Saved {shot6.name}")

        # Step 7: Management View (Training Policy & Review Queue)
        print("7. Switching to Duyệt dữ liệu huấn luyện (Training Policy & Review Queue)...")
        page.locator("#mgmtTabTraining").click()
        time.sleep(1.5)
        shot7 = OUT_DIR / "07_mgmt_training_policy.png"
        page.screenshot(path=str(shot7), full_page=False)
        print(f"   Saved {shot7.name}")

        # Step 8: Internal Messages View
        print("8. Navigating to Tin nhắn nội bộ...")
        page.locator("#navMessages").click()
        page.wait_for_selector("#viewMessages")
        time.sleep(1.5)
        shot8 = OUT_DIR / "08_internal_messages.png"
        page.screenshot(path=str(shot8), full_page=False)
        print(f"   Saved {shot8.name}")

        browser.close()
        print("Demo completed successfully! All screenshots captured.")


if __name__ == "__main__":
    run_demo()
