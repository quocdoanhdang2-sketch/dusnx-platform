#!/usr/bin/env python3
"""End-to-end verification for the Club IT assistant P0 fixes.

Runs against a live gateway (the secondary club stack listens on :8090):
- authenticates as the demo owner account (override with env vars)
- asks the demo questions plus the retrieval/extraction regressions
- asserts answer content, citations and the retrieval gate
- verifies the "So với API" comparison really reached the external API
- writes one JSON report per run under docs/evidence/club-demo-p0/

Read-only against the running stack: it creates its own chat sessions but
never restarts services or writes to the corpus. Exit code 1 when any case
fails so a failing run cannot be mistaken for evidence.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

# The demo accounts are documented test fixtures, not production secrets; they
# can still be overridden without editing this file.
DEMO_USER = os.getenv("DUSNX_DEMO_USER", "chunhiem")
DEMO_PASSWORD = os.getenv("DUSNX_DEMO_PASSWORD", "Admin@123456")

REFUSAL_MARKER = "Kho tài liệu và quy chế CLB IT chưa có thông tin"

CASES = [
    {
        "id": "CASE-1",
        "name": "Lab room rules (memory/RAG gate)",
        "query": "Quy định sử dụng phòng lab của CLB là gì?",
        "expected_top_doc": "06-quy-dinh-phong-lab.md",
        "expected_terms": ["A2-305", "cấm ăn uống"],
        "forbidden_terms": ["Tôi chưa đủ bối cảnh để chọn thông tin phù hợp", "Tôi chưa rõ"],
        "expect_provider_called": None,
        "expect_refusal": False,
    },
    {
        "id": "CASE-2",
        "name": "Club fee deadline & recipient (rerank)",
        "query": "Đóng quỹ trước ngày mấy và nộp cho ai?",
        "expected_top_doc": "16-dong-quy-clb.md",
        "expected_terms": ["trước ngày 10", "Phạm Thuỳ Dương"],
        "forbidden_terms": ["5.000.000", "hóa đơn VAT"],
        "expect_provider_called": False,
        "expect_refusal": False,
    },
    {
        "id": "CASE-3",
        "name": "Club monthly fee amount",
        "query": "Quỹ CLB đóng bao nhiêu một tháng?",
        "expected_top_doc": "16-dong-quy-clb.md",
        "expected_terms": ["50.000"],
        "forbidden_terms": ["5.000.000"],
        "expect_provider_called": False,
        "expect_refusal": False,
    },
    {
        "id": "CASE-4",
        "name": "IT CodeFest 2026 location (slot fill)",
        "query": "IT CodeFest 2026 tổ chức ở đâu?",
        "expected_top_doc": "04-it-codefest-2026.md",
        "expected_terms": ["sảnh tòa B"],
        "forbidden_terms": ["hội trường tòa C"],
        "expect_provider_called": False,
        "expect_refusal": False,
    },
    {
        "id": "CASE-5",
        "name": "Outstanding member criteria (slot fill)",
        "query": "Thành viên xuất sắc được đánh giá theo tiêu chí gì?",
        "expected_top_doc": "18-danh-gia-thanh-vien.md",
        "expected_terms": ["40%", "20%", "chuyên cần", "đóng góp", "thái độ"],
        "forbidden_terms": [],
        "expect_provider_called": False,
        "expect_refusal": False,
    },
    {
        "id": "CASE-6",
        "name": "Out-of-scope question (scope gate)",
        "query": "Giá vàng hôm nay bao nhiêu một chỉ?",
        "expected_top_doc": None,
        "expected_terms": [REFUSAL_MARKER],
        "forbidden_terms": [],
        "expect_provider_called": False,
        "expect_refusal": True,
    },
    {
        "id": "CASE-7",
        "name": "Recruitment wave 2 date range (milestone row)",
        "query": "Tuyển thành viên đợt 2 nhận đơn từ ngày nào đến ngày nào?",
        "expected_top_doc": "13-tuyen-thanh-vien-dot-2.md",
        "expected_terms": ["01/12/2026", "15/12/2026"],
        "forbidden_terms": [],
        "expect_provider_called": None,
        "expect_refusal": False,
    },
    {
        "id": "CASE-8",
        "name": "Workshop date in section heading",
        "query": "Workshop Git & GitHub tổ chức khi nào?",
        "expected_top_doc": "10-lich-workshop.md",
        "expected_terms": ["27/11/2026"],
        "forbidden_terms": [],
        "expect_provider_called": None,
        "expect_refusal": False,
    },
    {
        "id": "CASE-9",
        "name": "Team building overview (destination/date/fee)",
        "query": "Team building đi đâu, ngày nào, phí bao nhiêu?",
        "expected_top_doc": "17-team-building.md",
        "expected_terms": ["Thung Lũng Xanh", "27/12/2026", "100.000"],
        "forbidden_terms": [],
        "expect_provider_called": None,
        "expect_refusal": False,
    },
    {
        "id": "CASE-10",
        "name": "Lab registration procedure, not duration limit",
        "query": "Muốn dùng phòng lab phải đăng ký thế nào?",
        "expected_top_doc": "06-quy-dinh-phong-lab.md",
        "expected_terms": ["đăng ký trước ít nhất 1 ngày"],
        "forbidden_terms": ["3 tiếng"],
        "expect_provider_called": None,
        "expect_refusal": False,
    },
    {
        "id": "CASE-11",
        "name": "Capability question is not refused",
        "query": "Bạn làm được gì cho mình?",
        "expected_top_doc": None,
        "expected_terms": ["tài liệu", "nguồn"],
        "forbidden_terms": [REFUSAL_MARKER, "Người dùng:"],
        "expect_provider_called": False,
        "expect_refusal": False,
        "expect_sources_empty": True,
    },
    {
        "id": "CASE-12",
        "name": "Weather question refused",
        "query": "Thời tiết Hà Nội ngày mai thế nào?",
        "expected_top_doc": None,
        "expected_terms": [REFUSAL_MARKER],
        "forbidden_terms": [],
        "expect_provider_called": False,
        "expect_refusal": True,
    },
    {
        "id": "CASE-13",
        "name": "Self-trained model generation (LoRA / dusnx-vi-club)",
        "query": "Cảm ơn bạn rất nhiều!",
        "expected_top_doc": None,
        "expected_terms": [],
        "forbidden_terms": [
            REFUSAL_MARKER,
            "Người dùng:",
            "Hãy trả lời",
            "Câu hỏi của bạn là",
            "Yêu cầu người dùng",
        ],
        "expect_provider_called": True,
        "expect_source_type": "llm",
        "expect_provider": "ollama",
        "expect_model": "dusnx-vi-club",
        "expect_refusal": False,
        "expect_sources_empty": True,
    },
]


def http_post(url: str, payload: dict, token: str | None = None) -> dict:
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers=headers)
    with urllib.request.urlopen(req, timeout=120) as resp:
        return json.loads(resp.read().decode("utf-8"))


def http_get(url: str) -> dict:
    with urllib.request.urlopen(url, timeout=15) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _check_case(case: dict, resp: dict) -> list[str]:
    reply = resp.get("reply", "") or ""
    sources = resp.get("sources", []) or []
    top_source_path = sources[0].get("path") if sources else None
    provider_called = resp.get("provider_called")
    errors: list[str] = []

    if case["expect_refusal"]:
        if REFUSAL_MARKER.lower() not in reply.lower():
            errors.append("Expected a documented refusal, got a normal answer")
        if sources:
            errors.append(f"Refusal carried {len(sources)} sources")
    elif case.get("expect_sources_empty"):
        if sources:
            errors.append(f"Expected no sources, got {len(sources)}")
    elif case["expected_top_doc"]:
        if not top_source_path or case["expected_top_doc"] not in top_source_path:
            errors.append(f"Expected top doc {case['expected_top_doc']}, got {top_source_path}")
        if "[S1]" not in reply:
            errors.append("Answer has no [S1] citation")
        elif not sources:
            errors.append("Citation [S1] present but sources list is empty")

    for term in case["expected_terms"]:
        if term.lower() not in reply.lower():
            errors.append(f"Missing expected term: {term!r}")
    for term in case["forbidden_terms"]:
        if term.lower() in reply.lower():
            errors.append(f"Found forbidden term: {term!r}")
    if case["expect_provider_called"] is not None and provider_called != case["expect_provider_called"]:
        errors.append(
            f"Expected provider_called={case['expect_provider_called']}, got {provider_called}")
    if case.get("expect_provider") and resp.get("provider_used") != case["expect_provider"]:
        errors.append(
            f"Expected provider_used={case['expect_provider']!r}, got {resp.get('provider_used')!r}")
    if case.get("expect_model") and resp.get("model_used") != case["expect_model"]:
        errors.append(
            f"Expected model_used={case['expect_model']!r}, got {resp.get('model_used')!r}")
    if case.get("expect_source_type") and resp.get("response_source") != case["expect_source_type"]:
        errors.append(
            f"Expected response_source={case['expect_source_type']!r}, got {resp.get('response_source')!r}")
    return errors


def run_verification(base_url: str, run_idx: int) -> dict:
    print(f"=== Run #{run_idx} at {time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())} ===")
    health = http_get(f"{base_url}/health")
    print("Health:", {k: health.get(k) for k in ("status", "provider", "model_available")})

    login = http_post(f"{base_url}/v1/auth/login",
                      {"username": DEMO_USER, "password": DEMO_PASSWORD})
    token = login.get("token")
    if not token:
        raise SystemExit("Login failed: no token returned")
    assert login.get("role") == "owner", f"Unexpected role: {login.get('role')}"
    print(f"Logged in as {login.get('display_name')} ({login.get('role')})")

    session_id = http_post(f"{base_url}/v1/sessions",
                           {"title": f"P0 verify #{run_idx}"}, token=token)["session_id"]

    results = []
    for case in CASES:
        started = time.monotonic()
        resp = http_post(f"{base_url}/v1/chat",
                         {"session_id": session_id, "message": case["query"]}, token=token)
        wall_ms = round((time.monotonic() - started) * 1000, 1)
        errors = _check_case(case, resp)
        reply = resp.get("reply", "") or ""
        results.append({
            "id": case["id"],
            "name": case["name"],
            "query": case["query"],
            "passed": not errors,
            "errors": errors,
            "reply_preview": reply[:200] + ("..." if len(reply) > 200 else ""),
            "top_source": (resp.get("sources") or [{}])[0].get("path"),
            "source_type": resp.get("response_source"),
            "intent": resp.get("intent"),
            "provider_used": resp.get("provider_used"),
            "model_used": resp.get("model_used"),
            "provider_called": resp.get("provider_called"),
            "provider_elapsed_ms": resp.get("provider_elapsed_ms"),
            "wall_ms": wall_ms,
        })
        print(f"[{'PASS' if not errors else 'FAIL'}] {case['id']}: {case['name']}")
        for err in errors:
            print(f"       ERROR: {err}")
        print(f"       {reply[:110]}...")

    comp_req = {
        "session_id": session_id,
        "message": "Quỹ CLB đóng bao nhiêu một tháng?",
        "compare_with_api": True,
    }
    comp_res = http_post(f"{base_url}/v1/chat", comp_req, token=token)
    api_comp = comp_res.get("api_comparison")
    comp_errors = []
    if not api_comp:
        comp_errors.append("api_comparison block missing")
    else:
        if not api_comp.get("ok") or not api_comp.get("reply"):
            comp_errors.append(f"External API did not answer: {api_comp.get('error')}")
        if api_comp.get("provider_used") != "openai":
            comp_errors.append(f"provider_used={api_comp.get('provider_used')!r}, expected 'openai'")
        if not api_comp.get("tokens_generated"):
            comp_errors.append("No tokens reported from the external API")
        if comp_res.get("provider_used") not in ("ollama", None):
            comp_errors.append(
                f"Primary answer used {comp_res.get('provider_used')!r}, expected the local model/rag")
        primary_reply = comp_res.get("reply", "")
        if not primary_reply:
            comp_errors.append("Primary answer is empty")
        elif primary_reply.startswith("Người dùng:"):
            comp_errors.append("Primary answer repeated prompt with 'Người dùng:'")
    print(f"[{'PASS' if not comp_errors else 'FAIL'}] API comparison")
    for err in comp_errors:
        print(f"       ERROR: {err}")

    return {
        "run_idx": run_idx,
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "gateway": base_url,
        "all_passed": not comp_errors and all(r["passed"] for r in results),
        "total_cases": len(results),
        "passed_cases": sum(1 for r in results if r["passed"]),
        "cases": results,
        "api_comparison": {
            "passed": not comp_errors,
            "errors": comp_errors,
            "provider": (api_comp or {}).get("provider"),
            "provider_used": (api_comp or {}).get("provider_used"),
            "model": (api_comp or {}).get("model"),
            "tokens": (api_comp or {}).get("tokens_generated"),
            "latency_ms": (api_comp or {}).get("latency_ms"),
            "primary_provider": comp_res.get("provider_used"),
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Verify Club IT demo P0 fixes")
    parser.add_argument("--url", default=os.getenv("DUSNX_CLUB_GATEWAY", "http://127.0.0.1:8090"))
    parser.add_argument("--runs", type=int, default=3)
    parser.add_argument("--out-dir",
                        default=str(REPO_ROOT / "docs" / "evidence" / "club-demo-p0"))
    args = parser.parse_args()

    out_path = Path(args.out_dir)
    out_path.mkdir(parents=True, exist_ok=True)

    success = True
    for run_idx in range(1, args.runs + 1):
        try:
            report = run_verification(args.url, run_idx)
        except (urllib.error.URLError, SystemExit) as exc:
            print(f"Run #{run_idx} could not start: {exc}")
            success = False
            break
        log_file = out_path / f"run_{run_idx}.log"
        log_file.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"Saved {log_file}")
        success = success and report["all_passed"]

    if not success:
        print("Verification FAILED.")
        sys.exit(1)
    print(f"All {args.runs} runs passed ({len(CASES)} cases + API comparison each).")


if __name__ == "__main__":
    main()
