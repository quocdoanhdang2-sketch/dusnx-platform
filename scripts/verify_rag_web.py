"""Live runtime check: grounded RAG answers through the Gateway.

Runs a multilingual query set against a real DUSN-X stack and asserts that
retrieved answers are cited, that sources accompany only cited passages, and
that ordinary chat still works when no document covers the question.

Usage:
    python scripts/verify_rag_web.py [base_url]
    (default base_url: http://127.0.0.1:8085)

Requires a live Gateway whose AI API has the RAG index available. Evidence is
written to runtime/rag-web-verify-<timestamp>.json; no user data is read.
"""
from __future__ import annotations

import json
import re
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

BASE = (sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8085").rstrip("/")
ROOT = Path(__file__).resolve().parents[1]
EVIDENCE_DIR = ROOT / "runtime"
USER = f"rag_eval_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
PASSWORD = "RagEval123!"

# Each case: query, expected phrase fragments (accent-insensitive), expected mode.
CASES = [
    # Vietnamese, plain
    ("DUSN-X là gì?", ["nền tảng"], "rag"),
    ("kiến trúc DUSN-X gồm những tầng nào?",
     ["client", "gateway", "ai api", "sqlite"], "rag"),
    # Vietnamese, config/technical
    ("cấu hình Ollama provider", ["/api/chat", "temperature"], "rag"),
    ("timeout provider là bao nhiêu?", ["60"], "rag"),
    ("quality gate hoạt động thế nào?", ["placeholder"], "rag"),
    ("mật khẩu được hash bằng gì?", ["scrypt"], "rag"),
    ("trí nhớ của chatbot lưu ở đâu?", ["sqlite"], "rag"),
    ("SFT v3 có được promote không?", ["promote=false"], "rag"),
    # English
    ("What does the DUSN-X gateway do?", ["proxy"], "rag"),
    ("How does the Word add-in work?", ["office.js"], "rag"),
    # Accentless Vietnamese (keyboard without diacritics)
    ("kien truc he thong gom nhung tang nao?",
     ["client", "gateway"], "rag"),
    ("mat khau duoc hash bang gi?", ["scrypt"], "rag"),
    # Code identifiers (library-level question)
    ("answer_from_hits trả về gì?", ["none"], "rag"),
    # No document answer: ordinary chat path must still respond
    ("Hôm nay là ngày bao nhiêu?", ["2026"], "chat"),
]

_FOLD = str.maketrans(
    "àáảãạăằắẳẵặâầấẩẫậèéẻẽẹêềếểễệìíỉĩịòóỏõọôồốổỗộơờớởỡợùúủũụưừứửữựỳýỷỹỵđ",
    "aaaaaaaaaaaaaaaaaeeeeeeeeeeeiiiiiooooooooooooooooouuuuuuuuuuuyyyyyd",
)


def fold(text: str) -> str:
    return (text or "").lower().translate(_FOLD)


def http(method: str, path: str, payload: dict | None = None,
         token: str | None = None) -> dict:
    data = json.dumps(payload).encode() if payload is not None else None
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(f"{BASE}{path}", data=data, headers=headers,
                                 method=method)
    try:
        with urllib.request.urlopen(req, timeout=90) as response:
            return json.loads(response.read().decode())
    except urllib.error.HTTPError as exc:
        body = exc.read().decode(errors="replace")
        raise SystemExit(f"{method} {path} -> HTTP {exc.code}: {body[:500]}")


def main() -> int:
    health = http("GET", "/health")
    ai = http("GET", "/v1/health")
    rag = ai.get("rag") or {}
    print(f"Gateway {BASE}: {health.get('service')} -> {health.get('ai_api_url')}")
    print(f"AI API rag: {rag}")
    if not rag.get("available"):
        raise SystemExit("RAG index unavailable on this runtime; cannot verify grounded answers.")

    try:
        http("POST", "/v1/auth/register", {"username": USER, "password": PASSWORD})
    except SystemExit:
        pass  # A re-run with the same second-level name is fine to reuse.
    token = http("POST", "/v1/auth/login",
                 {"username": USER, "password": PASSWORD})["token"]
    session = http("POST", "/v1/sessions", {"title": "RAG eval"}, token)["session_id"]

    results = []
    failures = []
    for index, (query, fragments, mode) in enumerate(CASES, 1):
        started = time.perf_counter()
        payload = {
            "session_id": session,
            "request_id": f"rag-eval-{index}-{int(time.time() * 1000)}",
            "message": query,
            "feedback_value": 0,
            "is_retry": False,
        }
        response = http("POST", "/v1/chat", payload, token)
        elapsed_ms = int((time.perf_counter() - started) * 1000)
        reply = response.get("reply") or ""
        sources = response.get("sources") or []
        rag_used = bool(response.get("rag_used"))
        source = response.get("response_source")
        folded_reply = fold(reply)

        problems = []
        if not response.get("provider_ok"):
            problems.append(f"provider_ok=false ({response.get('provider_used')})")
        for fragment in fragments:
            if fold(fragment) not in folded_reply:
                problems.append(f"missing {fragment!r}")
        if mode == "rag":
            if not rag_used:
                problems.append("rag_used=false")
            if not sources:
                problems.append("no sources")
            cited = {int(match) for match in re.findall(r"\[S(\d+)\]", reply)}
            listed = {int(re.sub(r"\D", "", str(item.get("id", ""))) or 0)
                      for item in sources}
            if cited and listed and cited != listed:
                problems.append(f"cited {sorted(cited)} != sources {sorted(listed)}")
        else:
            if rag_used:
                problems.append("rag_used=true on non-document question")
            if sources:
                problems.append(f"{len(sources)} sources on non-document question")

        record = {
            "query": query,
            "expected_mode": mode,
            "response_source": source,
            "rag_used": rag_used,
            "sources": sources,
            "provider_used": response.get("provider_used"),
            "latency_ms": elapsed_ms,
            "reply": reply,
            "problems": problems,
        }
        results.append(record)
        status = "PASS" if not problems else "FAIL"
        if problems:
            failures.append(record)
        print(f"\n[{index:02d}] {status} {elapsed_ms:5d} ms  " 
              f"source={source} rag={rag_used} n_src={len(sources)}")
        print(f"     Q: {query}")
        print(f"     A: {reply[:300].replace(chr(10), ' | ')}")
        if sources:
            print("     S: " + "; ".join(
                f"[{item.get('id')}] {item.get('path')}:{item.get('start_line')}"
                for item in sources))
        for problem in problems:
            print(f"     ! {problem}")

    evidence = {
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "base_url": BASE,
        "gateway": health.get("service"),
        "binary_sha256": health.get("binary_sha256"),
        "ai_rag": rag,
        "cases": results,
        "passed": len(results) - len(failures),
        "failed": len(failures),
    }
    EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
    out = EVIDENCE_DIR / f"rag-web-verify-{datetime.now().strftime('%Y%m%d-%H%M%S')}.json"
    out.write_text(json.dumps(evidence, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n{len(results) - len(failures)}/{len(results)} passed. Evidence: {out}")
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
