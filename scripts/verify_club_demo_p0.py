#!/usr/bin/env python3
"""End-to-end verification script for Club IT Assistant P0 fixes.

Tests against the live gateway on port 8090:
- Authenticates as chunhiem / Admin@123456
- Executes all 6 fixed demo questions
- Asserts answer contents, citations, and source chips
- Verifies real Gemini API comparison call
- Outputs structured log
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.request
from pathlib import Path


def http_post(url: str, payload: dict, token: str | None = None) -> dict:
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers=headers)
    with urllib.request.urlopen(req, timeout=120) as resp:
        return json.loads(resp.read().decode("utf-8"))


def run_verification(base_url: str = "http://127.0.0.1:8090", run_idx: int = 1) -> dict:
    print(f"=== Starting Run #{run_idx} at {time.strftime('%Y-%m-%dT%H:%M:%SZ')} ===")
    
    # 1. Login as owner (chunhiem)
    login_res = http_post(f"{base_url}/v1/auth/login", {
        "username": "chunhiem",
        "password": "Admin@123456"
    })
    token = login_res.get("token")
    assert token, "Login failed: token is missing"
    assert login_res.get("role") == "owner", f"Unexpected role: {login_res.get('role')}"
    print(f"1. Logged in successfully as {login_res.get('username')} ({login_res.get('display_name')})")

    # 2. Create session
    sess_res = http_post(f"{base_url}/v1/sessions", {"title": f"P0 Verify Run {run_idx}"}, token=token)
    session_id = sess_res.get("session_id")
    assert session_id, "Session creation failed"
    print(f"2. Created session: {session_id}")

    test_cases = [
        {
            "id": "CASE-1",
            "name": "Lab room rules (Memory gate fix)",
            "query": "Quy định sử dụng phòng lab của CLB là gì?",
            "expected_top_doc": "06-quy-dinh-phong-lab.md",
            "expected_terms": ["phòng lab A2-305", "Tuyệt đối cấm ăn uống"],
            "forbidden_terms": ["Tôi chưa đủ bối cảnh để chọn thông tin phù hợp", "Tôi chưa rõ"],
            "expect_provider_called": None,
        },
        {
            "id": "CASE-2",
            "name": "Club fee deadline & recipient (Rerank fix)",
            "query": "Đóng quỹ trước ngày mấy và nộp cho ai?",
            "expected_top_doc": "16-dong-quy-clb.md",
            "expected_terms": ["trước ngày 10", "Phạm Thuỳ Dương"],
            "forbidden_terms": ["5.000.000", "hóa đơn VAT", "doc 24", "Nhóm 3"],
            "expect_provider_called": False,
        },
        {
            "id": "CASE-3",
            "name": "Club monthly fee amount",
            "query": "Quỹ CLB đóng bao nhiêu một tháng?",
            "expected_top_doc": "16-dong-quy-clb.md",
            "expected_terms": ["50.000"],
            "forbidden_terms": ["5.000.000"],
            "expect_provider_called": False,
        },
        {
            "id": "CASE-4",
            "name": "IT CodeFest 2026 location (Slot-filling fix)",
            "query": "IT CodeFest 2026 tổ chức ở đâu?",
            "expected_top_doc": "04-it-codefest-2026.md",
            "expected_terms": ["sảnh tòa B"],
            "forbidden_terms": [],
            "expect_provider_called": False,
        },
        {
            "id": "CASE-5",
            "name": "Outstanding member criteria (Slot-filling fix)",
            "query": "Thành viên xuất sắc được đánh giá theo tiêu chí gì?",
            "expected_top_doc": "18-danh-gia-thanh-vien.md",
            "expected_terms": ["40%", "20%", "chuyên cần", "đóng góp", "thái độ"],
            "forbidden_terms": [],
            "expect_provider_called": False,
        },
        {
            "id": "CASE-6",
            "name": "Out-of-scope question (Hard scope gate fix)",
            "query": "Giá vàng hôm nay bao nhiêu một chỉ?",
            "expected_top_doc": None,
            "expected_terms": ["Kho tài liệu và quy chế CLB IT chưa có thông tin về nội dung này"],
            "forbidden_terms": [],
            "expect_provider_called": False,
        },
    ]

    results = []
    for c in test_cases:
        chat_req = {
            "session_id": session_id,
            "message": c["query"],
        }
        resp = http_post(f"{base_url}/v1/chat", chat_req, token=token)
        reply = resp.get("reply", "")
        sources = resp.get("sources", [])
        top_source_path = sources[0].get("path") if sources else None
        provider_called = resp.get("provider_called")
        source_type = resp.get("response_source")

        # Assertions
        errors = []
        if c["expected_top_doc"]:
            if not top_source_path or c["expected_top_doc"] not in top_source_path:
                errors.append(f"Expected top doc {c['expected_top_doc']}, got {top_source_path}")
            # Verify [S1] in reply matches sources[0]
            if "[S1]" in reply and not sources:
                errors.append("Citation [S1] cited in text but sources list is empty")
        elif c["expected_top_doc"] is None and sources:
            # For out-of-scope refusal, sources must be empty
            if sources:
                errors.append(f"Expected empty sources for refused query, got {len(sources)} sources")

        for term in c["expected_terms"]:
            if term.lower() not in reply.lower():
                errors.append(f"Missing expected term: '{term}'")

        for term in c["forbidden_terms"]:
            if term.lower() in reply.lower():
                errors.append(f"Found forbidden term: '{term}'")

        if c["expect_provider_called"] is not None:
            if provider_called != c["expect_provider_called"]:
                errors.append(f"Expected provider_called={c['expect_provider_called']}, got {provider_called}")

        case_passed = len(errors) == 0
        case_summary = {
            "id": c["id"],
            "name": c["name"],
            "query": c["query"],
            "passed": case_passed,
            "errors": errors,
            "reply_preview": reply[:180] + ("..." if len(reply) > 180 else ""),
            "top_source": top_source_path,
            "source_type": source_type,
            "provider_called": provider_called,
        }
        results.append(case_summary)
        status_label = "PASS" if case_passed else "FAIL"
        print(f"[{status_label}] {c['id']}: {c['name']}")
        if not case_passed:
            for err in errors:
                print(f"       ERROR: {err}")
        print(f"       Reply preview: {reply[:100]}...")
        if top_source_path:
            print(f"       Top source chip: {top_source_path}")

    # 3. Verify Gemini API Comparison call
    print("\nVerifying 'So sánh với API' (Gemini comparison)...")
    comp_req = {
        "session_id": session_id,
        "message": "Hãy viết lời chào mừng thành viên mới gia nhập CLB IT",
        "compare_with_api": True,
    }
    comp_res = http_post(f"{base_url}/v1/chat", comp_req, token=token)
    api_comp = comp_res.get("api_comparison")
    assert api_comp is not None, "api_comparison block missing from response"
    assert api_comp.get("provider") == "openai", f"Expected provider 'openai' (Gemini proxy), got {api_comp.get('provider')}"
    assert "gemini-3.1-flash-lite" in api_comp.get("model", ""), f"Expected gemini-3.1-flash-lite, got {api_comp.get('model')}"
    assert api_comp.get("tokens_generated", 0) > 0, "No tokens returned from Gemini API"
    assert comp_res.get("provider_used") == "ollama", f"Primary answer should use ollama, got {comp_res.get('provider_used')}"
    print(f"[PASS] Gemini API comparison verified: provider={api_comp.get('provider')}, model={api_comp.get('model')}, tokens={api_comp.get('tokens_generated')}, latency={api_comp.get('latency_ms')}ms")

    all_passed = all(r["passed"] for r in results)
    run_report = {
        "run_idx": run_idx,
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "all_passed": all_passed,
        "total_cases": len(results),
        "passed_cases": sum(1 for r in results if r["passed"]),
        "failed_cases": sum(1 for r in results if not r["passed"]),
        "cases": results,
        "gemini_comparison": {
            "verified": True,
            "provider": api_comp.get("provider"),
            "model": api_comp.get("model"),
            "tokens": api_comp.get("tokens_generated"),
            "latency_ms": api_comp.get("elapsed_ms"),
        }
    }
    return run_report


def main():
    parser = argparse.ArgumentParser(description="Verify Club Demo P0 Fixes")
    parser.add_argument("--url", default="http://127.0.0.1:8090")
    parser.add_argument("--runs", type=int, default=3)
    parser.add_argument("--out-dir", default=r"D:\Projects\dusnx-platform\runtime\club-demo-verify")
    args = parser.parse_args()

    out_path = Path(args.out_dir)
    out_path.mkdir(parents=True, exist_ok=True)

    overall_success = True
    for r in range(1, args.runs + 1):
        report = run_verification(base_url=args.url, run_idx=r)
        log_file = out_path / f"run_{r}.log"
        log_file.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"Saved run report to {log_file}\n")
        if not report["all_passed"]:
            overall_success = False

    if not overall_success:
        print("Verification FAILED: One or more cases failed.")
        sys.exit(1)
    else:
        print(f"ALL {args.runs} RUNS PASSED SUCCESSFULLY! 6/6 demo cases consistent.")
        sys.exit(0)


if __name__ == "__main__":
    main()
