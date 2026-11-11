"""Provider SSE streaming and the /v1/chat/stream event contract."""
import json
import secrets
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from apps.ai_api import main, provider
from test_week2_acceptance import _register_and_login, client  # noqa: F401 (pytest fixtures)


class _FakeProvider(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def do_POST(self):
        length = int(self.headers.get("Content-Length") or 0)
        body = json.loads(self.rfile.read(length) or b"{}")
        if self.path == "/api/chat":
            assert body["stream"] is True
            self.send_response(200)
            self.send_header("Content-Type", "application/x-ndjson")
            self.end_headers()
            for item in ({"message": {"content": "Xin "}, "model": "fake"},
                         {"message": {"content": "chào"}, "model": "fake", "done": True,
                          "done_reason": "stop", "eval_count": 2}):
                self.wfile.write((json.dumps(item) + "\n").encode())
                self.wfile.flush()
        elif self.path == "/chat/completions":
            assert body["stream"] is True
            assert self.headers.get("Authorization") == "Bearer test-key"
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.end_headers()
            for event in ({"model": "fake", "choices": [{"delta": {"content": "Hel"}}]},
                          {"model": "fake", "choices": [{"delta": {"content": "lo"},
                                                         "finish_reason": "stop"}],
                           "usage": {"completion_tokens": 2}}):
                self.wfile.write(f"data: {json.dumps(event)}\n\n".encode())
                self.wfile.flush()
            self.wfile.write(b"data: [DONE]\n\n")
            self.wfile.flush()
        else:
            self.send_response(404)
            self.end_headers()


@pytest.fixture
def fake_provider(monkeypatch):
    server = ThreadingHTTPServer(("127.0.0.1", 0), _FakeProvider)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{server.server_address[1]}"
    monkeypatch.setenv("DUSNX_OLLAMA_URL", base)
    monkeypatch.setenv("DUSNX_OLLAMA_MODEL", "fake")
    monkeypatch.setattr(provider, "OPENAI_BASE_URL", base)
    monkeypatch.setattr(provider, "OPENAI_API_KEY", "test-key")
    monkeypatch.setattr(provider, "OPENAI_MODEL", "fake")
    yield base
    server.shutdown()
    server.server_close()


def test_ollama_stream_forwards_deltas(fake_provider):
    tokens = []
    result = provider._stream_ollama("system", "user", tokens.append,
                                     deadline=provider.time.monotonic() + 10)
    assert tokens == ["Xin ", "chào"]
    assert result[0] == "Xin chào" and result[1] is True
    assert result[3] == 2 and result.done_reason == "stop"
    assert result.diagnostics["stream"] is True and result.diagnostics["chunks"] == 2


def test_openai_stream_forwards_deltas(fake_provider):
    tokens = []
    result = provider._stream_openai("system", "user", tokens.append,
                                     deadline=provider.time.monotonic() + 10)
    assert tokens == ["Hel", "lo"]
    assert result[0] == "Hello" and result[1] is True and result[3] == 2


def test_generate_response_passes_tokens_and_skips_retry(fake_provider, monkeypatch):
    monkeypatch.setenv("DUSNX_PROVIDER", "ollama")
    tokens = []
    generated = provider.generate_response(
        user_message="Chào bạn", memories=[], intent="chat", response_language="vi",
        on_token=tokens.append)
    assert tokens == ["Xin ", "chào"]
    assert generated[0] == "Xin chào" and generated[1] is True
    assert generated.provider_called is True
    attempts = generated.provider_attempts
    assert attempts and all(not attempt.get("attempt") == 2 for attempt in attempts)


def _sse_frames(body: str):
    frames = []
    for block in body.split("\n\n"):
        if not block.strip():
            continue
        event, data = "message", ""
        for line in block.splitlines():
            if line.startswith("event:"):
                event = line[6:].strip()
            elif line.startswith("data:"):
                data += line[5:].strip()
        frames.append((event, json.loads(data) if data else None))
    return frames


def test_chat_stream_endpoint_emits_tokens_then_done(client, monkeypatch):  # noqa: F811
    _, token = _register_and_login(client, "stream_endpoint")
    headers = {"Authorization": f"Bearer {token}"}
    session_id = client.post("/v1/sessions", headers=headers, json={}).json()["session_id"]

    def fake_generate(**kwargs):
        emit = kwargs.get("on_token")
        assert emit is not None
        emit("Xin ")
        emit("chào")
        result = provider.ProviderResult("Xin chào", True, "ollama", "fake", 2, called=True)
        result.response_source = "llm"
        return result

    monkeypatch.setattr(main, "generate_response", fake_generate)
    payload = {"session_id": session_id, "message": "Kể chuyện tưởng tượng về rồng xanh",
               "request_id": secrets.token_hex(16)}
    with client.stream("POST", "/v1/chat/stream", headers=headers, json=payload) as response:
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/event-stream")
        frames = _sse_frames("".join(response.iter_text()))

    tokens = [data["text"] for event, data in frames if event == "token"]
    done = [data for event, data in frames if event == "done"]
    assert tokens == ["Xin ", "chào"]
    assert len(done) == 1 and done[0]["reply"] == "Xin chào" and done[0]["provider_ok"] is True

    # Same request id is replayed from the durable receipt, not regenerated.
    with client.stream("POST", "/v1/chat/stream", headers=headers, json=payload) as replay:
        replay_frames = _sse_frames("".join(replay.iter_text()))
    replay_done = [data for event, data in replay_frames if event == "done"][0]
    assert replay_done["replayed"] is True and replay_done["provider_called"] is False


def test_chat_stream_fast_path_returns_single_done(client, monkeypatch):  # noqa: F811
    _, token = _register_and_login(client, "stream_fastpath")
    headers = {"Authorization": f"Bearer {token}"}
    session_id = client.post("/v1/sessions", headers=headers, json={}).json()["session_id"]
    monkeypatch.setattr(main, "generate_response",
                        lambda **kwargs: pytest.fail("provider must not run for a clock question"))
    with client.stream("POST", "/v1/chat/stream", headers=headers,
                       json={"session_id": session_id, "message": "Hôm nay là ngày mấy?"}) as response:
        frames = _sse_frames("".join(response.iter_text()))
    assert not [data for event, data in frames if event == "token"]
    done = [data for event, data in frames if event == "done"]
    assert len(done) == 1 and done[0]["provider_ok"] is True
