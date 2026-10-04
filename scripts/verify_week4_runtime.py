"""Real native Gateway acceptance with isolated failure processes and SQLite cross-checks.

Never evaluates benchmark/holdout data; no credentials enter evidence or process args.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import secrets
import socket
import sqlite3
import subprocess
import sys
import time

import httpx

ROOT = Path(__file__).resolve().parents[1]
CHECKPOINT = ROOT / "training-results/colab-run-01/extracted/dusnx-router-full-01/router.pt"


def free_port():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


class Stack:
    """Own only the exact child processes created here; main/native services stay intact."""
    def __init__(self, directory, **config):
        self.directory = directory
        self.directory.mkdir(parents=True, exist_ok=False)
        self.ai_port, self.gw_port = free_port(), free_port()
        self.url = f"http://127.0.0.1:{self.gw_port}"
        self.env = {**os.environ, "PYTHONPATH": str(ROOT / "python") + os.pathsep + str(ROOT / "python/src"),
                    "DUSNX_DATA_DIR": str(directory / "ai"), "DUSNX_CHECKPOINT": str(CHECKPOINT),
                    "DUSNX_DEVICE": "cpu", "DUSNX_PROVIDER": "ollama", "DUSNX_OLLAMA_MODEL": "qwen2.5:0.5b",
                    "DUSNX_ENABLE_LLM_EVAL": "0", **config}
        self.processes = []
        self.logs = []

    def __enter__(self):
        try:
            self.start([sys.executable, "-m", "uvicorn", "apps.ai_api.main:app", "--host", "127.0.0.1", "--port", str(self.ai_port)], self.env, "ai")
            self.wait(f"http://127.0.0.1:{self.ai_port}/health", "dusnx-ai-api")
            env = {**self.env, "AI_API_URL": f"http://127.0.0.1:{self.ai_port}",
                   "DUSNX_DATA_DIR": str(self.directory / "gateway"), "DUSNX_WEB_UI_DIR": str(ROOT / "web-ui")}
            self.start(["dotnet", str(ROOT / "gateway-dotnet/bin/Release/net8.0/Dusnx.Gateway.dll"), "--urls", self.url], env, "gateway")
            self.wait(self.url + "/health", "dusnx-gateway")
            return self
        except Exception:
            self.__exit__(None, None, None)
            raise

    def start(self, args, env, name):
        log = (self.directory / f"{name}.log").open("w", encoding="utf-8")
        self.logs.append(log)
        self.processes.append(subprocess.Popen(args, cwd=ROOT, env=env, stdout=log, stderr=log))

    def wait(self, url, service):
        with httpx.Client(trust_env=False) as c:
            for _ in range(120):
                if any(p.poll() is not None for p in self.processes):
                    raise RuntimeError("Owned acceptance process exited during startup")
                try:
                    if c.get(url, timeout=2).json().get("service") == service:
                        return
                except (httpx.HTTPError, ValueError):
                    pass
                time.sleep(.25)
        raise RuntimeError("Native test process startup timeout")

    def __exit__(self, *args):
        for process in reversed(self.processes):
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(10)
                except subprocess.TimeoutExpired:
                    process.kill()  # Exact child handle only.
                    process.wait(5)
        for log in self.logs:
            log.close()


class API:
    def __init__(self, url):
        self.client = httpx.Client(base_url=url, timeout=120, trust_env=False)
        self.headers = {}

    def call(self, method, path, status=200, **kwargs):
        r = self.client.request(method, path, headers=self.headers, **kwargs)
        if r.status_code != status:
            raise AssertionError(f"{method} {path.split('?')[0]}: expected {status}, received {r.status_code}")
        return r.json() if r.content and status != 204 else None

    def login_new(self):
        creds = dict(username="w4_" + secrets.token_hex(8), password=secrets.token_urlsafe(24))
        self.call("POST", "/v1/auth/register", status=201, json=creds)
        self.headers = {"Authorization": "Bearer " + self.call("POST", "/v1/auth/login", json=creds)["token"]}
        return self.call("GET", "/v1/auth/me")["user_id"]

    def session(self):
        return self.call("POST", "/v1/sessions", status=201, json={"title": "Week 4 synthetic acceptance"})["session_id"]

    def chat(self, sid, text, request_id=None, retry=False):
        return self.call("POST", "/v1/chat", json={"session_id": sid, "message": text,
                         "request_id": request_id or secrets.token_hex(16), "is_retry": retry})

    def close(self):
        try:
            if self.headers:
                self.call("POST", "/v1/auth/logout")
        finally:
            self.client.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--gateway", default="http://127.0.0.1:8080")
    parser.add_argument("--data-dir", required=True, help="Main acceptance AI DB directory, never a personal DB")
    parser.add_argument("--output-dir", required=True, help="Must be new")
    args = parser.parse_args()
    out = Path(args.output_dir).resolve()
    out.mkdir(parents=True, exist_ok=False)
    report = dict(timestamp_utc=datetime.now(timezone.utc).isoformat(), transport="real_native_http_gateway",
                  gateway=args.gateway, checks={}, responses={}, failure_processes="isolated_new_databases")
    checks = report["checks"]
    def record(name, r):
        report["responses"][name] = {k: r.get(k) for k in ("reply", "intent", "next_action", "provider_ok", "provider_called",
           "provider_used", "model_used", "response_source", "state_version", "candidate_memory_ids", "prompt_memory_ids", "memory_ids_used")}
    a, b = API(args.gateway), API(args.gateway)
    try:
        health = a.call("GET", "/v1/health")
        report["health"] = {k: health[k] for k in ("service", "api_contract", "runtime_mode", "checkpoint_loaded", "model_loaded", "checkpoint_path", "model_version", "provider_ok", "provider")}
        report["checkpoint_sha256"] = hashlib.sha256(CHECKPOINT.read_bytes()).hexdigest()
        assert report["checkpoint_sha256"] == "56f56e6d61afc264fb02d690d2872fb3ac5db9749a659c8493fd9d99eab7e7b1"
        assert health["runtime_mode"] == "trained_dusnx" and health["checkpoint_loaded"] and health["provider_ok"]
        assert health["provider"]["configured_model"] == "qwen2.5:0.5b"
        assert {"qwen2.5:0.5b", "dusnx-vi-candidate:latest"} <= set(health["provider"]["models_available"])
        uid = a.login_new()
        b.login_new()
        sid = a.session()
        save_key = secrets.token_hex(16)
        first = a.chat(sid, "Hãy nhớ rằng chúng tôi chọn PostgreSQL cho cơ sở dữ liệu.", save_key)
        mid = first["memory_ids_used"][0]
        replay = a.chat(sid, "Hãy nhớ rằng chúng tôi chọn PostgreSQL cho cơ sở dữ liệu.", save_key, True)
        assert replay["message_id"] == first["message_id"] and replay["reply"] == first["reply"]
        assert replay["replayed"] and not replay["provider_called"] and replay["response_source"] == "replay"
        assert len(a.call("GET", "/v1/memories")) == 1
        db_path = Path(args.data_dir).resolve() / "memory.db"
        with sqlite3.connect(f"file:{db_path.as_posix()}?mode=ro", uri=True) as db:
            row = db.execute("SELECT content,version,is_active FROM memories WHERE memory_id=? AND user_id=?", (mid, uid)).fetchone()
            assert row and "PostgreSQL" in row[0] and row[1:] == (1, 1)
        checks["RT-02"] = "passed: save + durable replay + read-only SQLite"
        change = a.chat(sid, "Đổi PostgreSQL sang MongoDB")
        assert change["next_action"] == "await_confirm"
        assert "PostgreSQL" in a.call("GET", f"/v1/memories/{mid}")["content"]
        confirm_key = secrets.token_hex(16)
        confirm = a.chat(sid, "Đồng ý", confirm_key)
        new_id = confirm["memory_ids_used"][0]
        old = a.call("GET", f"/v1/memories/{mid}")
        new = a.call("GET", f"/v1/memories/{new_id}")
        assert not old["is_active"] and old["superseded_by"] == new_id and new["is_active"] and new["version"] == 2
        assert "cơ sở dữ liệu" in new["content"] and "MongoDB" in new["content"]
        with sqlite3.connect(f"file:{db_path.as_posix()}?mode=ro", uri=True) as db:
            versions = db.execute("SELECT version,is_active FROM memories WHERE user_id=? ORDER BY version", (uid,)).fetchall()
            assert versions == [(1, 0), (2, 1)]
        checks["RT-03"] = "passed: pending + atomic supersede API/SQLite + complete topic"
        state_before = a.call("GET", "/v1/me/state")
        messages_before = a.call("GET", f"/v1/sessions/{sid}/messages")
        repeated = a.chat(sid, "Đồng ý", confirm_key, True)
        assert repeated["message_id"] == confirm["message_id"] and repeated["reply"] == confirm["reply"] and repeated["replayed"]
        assert a.call("GET", "/v1/me/state") == state_before
        assert a.call("GET", f"/v1/sessions/{sid}/messages") == messages_before
        checks["RT-08"] = "passed: no added memory/message/state/version on confirmation replay"
        a.chat(sid, "Đổi MongoDB sang SQLite")
        rejected = a.chat(sid, "Không đồng ý")
        assert rejected["intent"] == "decision_update_cancelled"
        assert a.call("GET", f"/v1/memories/{new_id}") == new
        checks["RT-04"] = "passed: rejected proposal preserves active record"
        a.chat(sid, "Hãy nhớ rằng chúng tôi chọn AWS cho hạ tầng đám mây.")
        sid2 = a.session()
        for name, text, fact, excluded in [
            ("database", "Cơ sở dữ liệu được chọn là gì?", "MongoDB", "AWS"),
            ("cloud", "Hạ tầng đám mây được chọn là gì?", "AWS", "MongoDB")]:
            r = a.chat(sid2, text); record(name, r)
            assert fact in r["reply"] and excluded not in r["reply"]
            assert r["response_source"] == "grounded_template" and not r["provider_called"]
            assert len(r["memory_ids_used"]) == 1 and len(r["candidate_memory_ids"]) == 2 and r["prompt_memory_ids"] == []
        checks["RT-05"] = "passed: two decision records selected by topic, separate evidence/candidates"
        checks["RT-07"] = "passed: new session recalls current facts only"
        ambiguous = a.chat(sid2, "Quyết định hiện tại của tôi là gì?"); record("ambiguous", ambiguous)
        assert ambiguous["next_action"] == "clarify" and ambiguous["memory_ids_used"] == [] and not ambiguous["provider_called"]
        checks["RT-06"] = "passed: ambiguous question asks clarification"
        foreign = [
            ("GET", f"/v1/memories/{new_id}", None), ("DELETE", f"/v1/memories/{new_id}", None),
            ("PUT", f"/v1/memories/{new_id}", {"content": "intruder"}),
            ("GET", f"/v1/sessions/{sid}", None), ("GET", f"/v1/sessions/{sid}/messages", None),
            ("DELETE", f"/v1/sessions/{sid}", None), ("POST", "/v1/chat", {"session_id": sid, "message": "intruder"})]
        for method, path, payload in foreign:
            b.call(method, path, status=404, **({"json": payload} if payload else {}))
        proposal = a.chat(sid2, "Đổi MongoDB sang MariaDB")
        assert proposal["next_action"] == "await_confirm"
        pending = a.call("GET", f"/v1/pending-decisions?session_id={sid2}")[0]
        assert b.call("GET", f"/v1/pending-decisions?session_id={sid2}") == []
        b.call("POST", f"/v1/pending-decisions/{pending['pending_id']}/resolve", status=404, json={"accepted": True})
        assert b.call("GET", "/v1/memories") == [] and b.call("GET", "/v1/me/state")["state_version"] == 0
        checks["RT-09"] = "passed: foreign memory/session/pending denied and state isolated"
        a.call("POST", f"/v1/pending-decisions/{pending['pending_id']}/resolve", json={"accepted": False})
        route = a.call("POST", "/api/v1/llm-evaluation", status=404, json={"model": "qwen2.5:0.5b",
                         "messages": [{"role": "system", "content": "Tiếng Việt"}, {"role": "user", "content": "Chào"}]})
        assert route["detail"] == "LLM evaluation is disabled"
        assert a.call("GET", "/health")["api_contract"] == "week4-v1"
        checks["RT-14"] = "passed: new binary route reaches disabled authenticated FastAPI endpoint"
        token = b.headers["Authorization"]
        b.headers["Authorization"] = "Bearer invalid-synthetic-token"
        b.call("GET", "/v1/memories", status=401)
        b.headers["Authorization"] = token
        b.call("POST", "/v1/auth/logout")
        b.call("GET", "/v1/me/state", status=401)
        b.headers = {}
        checks["RT-12"] = "passed: invalid and revoked tokens denied; expiry tested below"
        # Delete test memory and ensure inactive evidence is not reused.
        a.call("DELETE", f"/v1/memories/{new_id}", status=204)
        deleted = a.chat(a.session(), "Cơ sở dữ liệu được chọn là gì?")
        assert new_id not in deleted["candidate_memory_ids"] and new_id not in deleted["memory_ids_used"]
        checks["memory_delete"] = "passed: deleted information excluded from retrieval and answer evidence"
        manual = a.call("POST", "/v1/memories", status=201,
                        json={"info_type": "decision", "content": "Chọn trà sen cho đồ uống."})
        edited = a.call("PUT", f"/v1/memories/{manual['memory_id']}", json={"content": "Chọn trà đào cho đồ uống."})
        a.call("PUT", f"/v1/memories/{manual['memory_id']}", status=404, json={"content": "Chọn cà phê cho đồ uống."})
        assert edited["version"] == 2 and len([m for m in a.call("GET", "/v1/memories") if "đồ uống" in m["content"]]) == 1
        checks["direct_update"] = "passed: inactive original cannot fork a second active version"
        generation_session = a.session()
        generation_key = secrets.token_hex(16)
        generated = a.chat(generation_session, "Viết một câu ngắn về đọc sách.", generation_key)
        assert generated["provider_ok"] and generated["provider_called"] and generated["response_source"] == "llm"
        state_before = a.call("GET", "/v1/me/state")
        replay = a.chat(generation_session, "Viết một câu ngắn về đọc sách.", generation_key, True)
        assert replay["message_id"] == generated["message_id"] and replay["reply"] == generated["reply"]
        assert replay["replayed"] and replay["response_source"] == "replay" and not replay["provider_called"]
        assert replay["provider_used"] is None and replay["model_used"] is None
        assert replay["original_provenance"]["model_used"] == "qwen2.5:0.5b"
        assert a.call("GET", "/v1/me/state") == state_before
        checks["llm_replay"] = "passed: cached generated text preserves original evidence but does not claim another Ollama call"

        for name, config, expected in [
            ("offline", {"DUSNX_OLLAMA_URL": f"http://127.0.0.1:{free_port()}"}, "unreachable"),
            ("missing-model", {"DUSNX_OLLAMA_MODEL": "dusnx-deliberately-missing-week4:never"}, "model_missing")]:
            with Stack(out / name, **config) as stack:
                api = API(stack.url)
                try:
                    h = api.call("GET", "/v1/health")
                    assert not h["provider_ok"] and not h["provider"]["available"]
                    api.login_new(); s = api.session()
                    r = api.chat(s, "Viết một câu chào bằng tiếng Việt."); record(name, r)
                    assert not r["provider_ok"] and r["provider_called"] and r["response_source"] == "provider_error"
                    assert r["model_used"] is None and expected in r["reply"]
                    assert all(m["role"] == "user" for m in api.call("GET", f"/v1/sessions/{s}/messages"))
                    checks["RT-10" if name == "offline" else "RT-11"] = "passed: isolated native Gateway error, no successful assistant record"
                finally:
                    api.close()
        for name, path in [("checkpoint-missing", out / "no-router.pt"), ("checkpoint-invalid", out / "invalid-router.pt")]:
            if name == "checkpoint-invalid":
                path.write_bytes(b"invalid isolated checkpoint fixture")
            with Stack(out / name, DUSNX_CHECKPOINT=str(path)) as stack:
                api = API(stack.url)
                try:
                    h = api.call("GET", "/v1/health")
                    assert h["runtime_mode"] == "bootstrap_rules" and not h["checkpoint_loaded"] and not h["model_loaded"] and h["checkpoint_path"] is None
                    report.setdefault("checkpoint_failures", {})[name] = {k: h[k] for k in ("runtime_mode", "checkpoint_loaded", "model_loaded", "model_version")}
                finally:
                    api.close()
        checks["RT-15"] = "passed: missing and invalid isolated checkpoints never claim trained runtime"
        with Stack(out / "invalid-state") as stack:
            api = API(stack.url)
            try:
                test_uid = api.login_new()
                with sqlite3.connect(stack.directory / "ai/memory.db") as db:
                    db.execute("INSERT INTO dusnx_state VALUES(?,?,?,?)", (test_uid, '{"global_state":"invalid"}', 5, datetime.now(timezone.utc).isoformat()))
                visible = api.call("GET", "/v1/me/state")
                assert not visible["state_compatible"] and visible["reset_reason"] == "invalid_state_schema"
                api.call("POST", "/v1/me/events", status=409, json={"platform": "web", "content": "state safety"})
                assert api.call("GET", "/v1/me/state")["state_version"] == 5
                assert api.call("GET", "/v1/me/events")["events"] == []
                checks["state_schema"] = "passed: invalid isolated stored state is visible and rejected without silent reuse"
            finally:
                api.close()
        with Stack(out / "expiry", DUSNX_TOKEN_TTL_SECONDS="1") as stack:
            api = API(stack.url)
            try:
                api.login_new(); time.sleep(1.3)
                api.call("GET", "/v1/me/state", status=401)
                checks["RT-12"] += "; real 1-second expiry denied"
                api.headers = {}
            finally:
                api.close()
        # An unrelated server is deliberately on the requested Gateway port.
        port = free_port()
        log = (out / "foreign-port.log").open("w")
        foreign = subprocess.Popen([sys.executable, "-m", "http.server", str(port), "--bind", "127.0.0.1"], cwd=out, stdout=log, stderr=log)
        try:
            with httpx.Client(trust_env=False) as probe:
                for _ in range(80):
                    try:
                        if probe.get(f"http://127.0.0.1:{port}", timeout=1).status_code == 200:
                            break
                    except httpx.HTTPError:
                        pass
                    time.sleep(.1)
                else:
                    raise RuntimeError("Unrelated port fixture failed to start")
            env = {**os.environ, "DUSNX_DEVICE": "cpu", "DUSNX_PROVIDER": "ollama", "DUSNX_ENABLE_LLM_EVAL": "0"}
            result = subprocess.run(["powershell", "-ExecutionPolicy", "Bypass", "-File", str(ROOT / "start-local.ps1"),
                    "-AiPort", str(free_port()), "-GatewayPort", str(port), "-AiDataDir", str(out / "unused-ai")],
                    cwd=ROOT, env=env, capture_output=True, text=True, timeout=30)
            assert result.returncode != 0 and foreign.poll() is None
            # Python HTTP server returns 404 for /health: this is identity-unverified,
            # while an unrelated JSON health server is explicitly not DUSN-X.
            assert "identity unverified" in result.stderr or "not DUSN-X Gateway" in result.stderr
            assert "No process was stopped" in result.stderr or "no process was stopped" in result.stderr
            assert "Started FastAPI" not in result.stdout and "Started Gateway" not in result.stdout
            checks["RT-16"] = "passed: unrelated port owner rejected and remains running"
        finally:
            foreign.terminate(); foreign.wait(10); log.close()
        assert a.call("GET", "/v1/health")["provider_ok"]
        assert hashlib.sha256(CHECKPOINT.read_bytes()).hexdigest() == report["checkpoint_sha256"]
        checks["restoration"] = "passed: main stack healthy, base default, original checkpoint unchanged"
        report["status"] = "passed"
    except Exception as exc:
        report["status"] = "failed"
        report["error"] = type(exc).__name__ + ": " + str(exc)
    finally:
        for api in (a, b):
            try:
                api.close()
            except Exception:
                pass
        (out / "runtime.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.exit(main())
