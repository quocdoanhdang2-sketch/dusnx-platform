"""Measure an isolated real stack; never treats local reads as generation/load acceptance."""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import subprocess
import time

import httpx

from verify_week4_runtime import API, ROOT, Stack


def source_identity():
    def git(*args):
        return subprocess.check_output(["git", *args], cwd=ROOT)
    patch = git("diff", "--binary", "HEAD")
    return {"head_sha": git("rev-parse", "HEAD").decode().strip(),
            "tracked_dirty": bool(patch), "tracked_patch_sha256": hashlib.sha256(patch).hexdigest(),
            "harness_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}


def measure(client, path, requests, concurrency):
    def call(_):
        started = time.perf_counter()
        try:
            response = client.get(path)
            return (time.perf_counter() - started) * 1000, response.status_code
        except httpx.HTTPError:
            return (time.perf_counter() - started) * 1000, "transport_error"
    started = time.perf_counter()
    with ThreadPoolExecutor(max_workers=concurrency) as pool:
        samples = list(pool.map(call, range(requests)))
    seconds = time.perf_counter() - started
    durations = sorted(ms for ms, _ in samples)
    statuses = {}
    for _, status in samples:
        statuses[str(status)] = statuses.get(str(status), 0) + 1
    return {"requests": requests, "concurrency": concurrency, "wall_seconds": seconds,
            "p50_ms": durations[math.ceil(.5 * requests) - 1],
            "p95_ms": durations[math.ceil(.95 * requests) - 1],
            "requests_per_second": requests / seconds, "statuses": statuses,
            "all_http_200": all(status == 200 for _, status in samples)}


def browser_csp(url, executable):
    from playwright.sync_api import sync_playwright, expect
    with sync_playwright() as pw:
        browser = pw.chromium.launch(executable_path=executable, headless=True, args=["--no-sandbox"])
        try:
            page = browser.new_page()
            page.goto(url)
            expect(page.locator("#loginForm")).to_be_visible()
            page.locator("#tabRegister").click()
            expect(page.locator("#registerForm")).to_be_visible()
            page.locator("#tabLogin").click()
            expect(page.locator("#loginForm")).to_be_visible()
            return page.evaluate("""async () => {
              const violations = [];
              document.addEventListener('securitypolicyviolation', e => violations.push(e.effectiveDirective));
              window.__dusnxInlineProbe = false;
              const script = document.createElement('script');
              script.textContent = 'window.__dusnxInlineProbe = true';
              document.body.appendChild(script);
              const button = document.createElement('button');
              button.setAttribute('onclick', 'window.__dusnxInlineProbe = true');
              document.body.appendChild(button); button.click();
              await new Promise(resolve => setTimeout(resolve, 100));
              script.remove(); button.remove();
              return {external_actions_work: true, inline_execution_blocked: window.__dusnxInlineProbe === false,
                      blocked_script: violations.includes('script-src-elem'),
                      blocked_handler: violations.includes('script-src-attr')};
            }""")
        finally:
            browser.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--requests", type=int, default=20)
    parser.add_argument("--concurrency", type=int, default=4)
    parser.add_argument("--chromium", default="/usr/bin/chromium")
    args = parser.parse_args()
    if not 1 <= args.requests <= 24 or not 1 <= args.concurrency <= 8:
        parser.error("Use 1–24 requests/workload and 1–8 workers for this bounded local probe")
    out = Path(args.output_dir).resolve()
    out.mkdir(parents=True, exist_ok=False)
    report = {"timestamp_utc": datetime.now(timezone.utc).isoformat(), "code": source_identity(),
              "scope": "isolated_local_http_reads_and_browser_csp", "llm_generation_verified": False,
              "production_capacity_verified": False, "protected_data_accessed": False}
    try:
        with Stack(out / "read-stack", DUSNX_OLLAMA_URL="http://127.0.0.1:9",
                   DUSNX_RATE_LIMIT_PER_MINUTE="120") as stack:
            api = API(stack.url)
            try:
                api.login_new()
                sid = api.session()
                with httpx.Client(base_url=stack.url, headers=api.headers, trust_env=False, timeout=30) as client:
                    health = client.get("/v1/health").json()
                    report["runtime"] = {k: health.get(k) for k in
                                         ("service", "runtime_mode", "checkpoint_loaded", "provider_ok")}
                    assert health.get("service") == "dusnx-ai-api", "Wrong service on upstream route"
                    assert health.get("checkpoint_loaded"), "Trained checkpoint unavailable"
                    report["workloads"] = {name: measure(client, path, args.requests, args.concurrency)
                        for name, path in (("gateway_health", "/health"), ("authenticated_memories", "/v1/memories"),
                                           ("authenticated_history", f"/v1/sessions/{sid}/messages/page"))}
                    csp = client.get("/").headers.get("content-security-policy", "")
                    script_policy = next((x.strip() for x in csp.split(";") if x.strip().startswith("script-src ")), "")
                    report["csp"] = {"script_policy": script_policy,
                                     "unsafe_inline_script_allowed": "'unsafe-inline'" in script_policy,
                                     "inline_attributes_denied": "script-src-attr 'none'" in csp,
                                     "browser": browser_csp(stack.url, args.chromium)}
            finally:
                api.close()
        with Stack(out / "rate-stack", DUSNX_OLLAMA_URL="http://127.0.0.1:9",
                   DUSNX_RATE_LIMIT_PER_MINUTE="6") as limited:
            with httpx.Client(base_url=limited.url, trust_env=False, timeout=10) as client:
                statuses = [client.get("/health").status_code for _ in range(10)]
                report["rate_limit"] = {"configured_requests_per_minute": 6,
                                        "observed_statuses": statuses, "http_429_observed": 429 in statuses}
        assert all(x["all_http_200"] for x in report["workloads"].values()), "Read workload failed"
        assert not report["csp"]["unsafe_inline_script_allowed"], "Inline script remains allowed"
        assert report["csp"]["inline_attributes_denied"], "Missing script-src-attr guard"
        assert all(report["csp"]["browser"].values()), "Browser CSP enforcement or external handlers failed"
        assert report["rate_limit"]["http_429_observed"], "Runtime rate limit not enforced"
        report["status"] = "passed"
    except Exception as exc:
        report.update(status="failed", failure_type=type(exc).__name__, failure=str(exc))
        raise
    finally:
        (out / "report.json").write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
        print(json.dumps(report, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
