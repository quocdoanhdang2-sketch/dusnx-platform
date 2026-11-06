import hashlib
import json
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

MODEL = "dusnx-vi-candidate:latest"
OLLAMA = "http://127.0.0.1:11434"
OUTPUT = Path("runtime/ollama-candidate-compare-20261104-r2")


def post(path: str, payload: dict, timeout: int = 10) -> dict:
    body = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode()
    request = urllib.request.Request(OLLAMA + path, data=body,
        headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.load(response)


OUTPUT.mkdir(parents=True, exist_ok=False)
tags = json.load(urllib.request.urlopen(OLLAMA + "/api/tags", timeout=10))
model_entry = next((item for item in tags.get("models", [])
                    if item.get("name") == MODEL), {})
show = post("/api/show", {"model": MODEL})
model_info = show.get("model_info", {})
report = {
    "probe_id": "DUSNX_VI_CANDIDATE_DIRECT_TASK_COMPARISON_R2",
    "created_at_utc": datetime.now(timezone.utc).isoformat(),
    "transport": "direct Ollama /api/chat; not Gateway or browser",
    "model_tag": MODEL,
    "model_digest": model_entry.get("digest"),
    "ollama_version": "0.40.14",
    "model_metadata": {
        "details": show.get("details", {}),
        "parameters": show.get("parameters"),
        "architecture": model_info.get("general.architecture"),
        "parameter_count": model_info.get("general.parameter_count"),
        "quantization": model_info.get("general.file_type"),
        "template_sha256": hashlib.sha256((show.get("template") or "").encode()).hexdigest(),
        "raw_modelfile_or_template_saved": False,
    },
    "fixed_settings": {"temperature": 0.1, "num_predict": 512,
        "repeat_penalty": 1.25, "repeat_last_n": 64, "num_ctx": 4096,
        "timeout_seconds": 65, "stream": False, "think_field": "omitted"},
    "cases": [
        {"id": "TRANSLATE_ENTITIES_EN",
         "system": "Translate the user request into English. Preserve exact URLs and KEY=VALUE literals. Do not include analysis.",
         "user": "Translate this sentence to English: Dịch vụ https://service.example.net/v2 dùng biến DUSNX_PORT=8188 để nhận kết nối."},
        {"id": "API_GATEWAY_BENEFIT_VI",
         "system": "Trả lời ngắn gọn bằng tiếng Việt. Không lặp lại hướng dẫn hoặc nêu phân tích.",
         "user": "Nêu một lợi ích cụ thể của API Gateway trong kiến trúc microservices."},
    ],
    "trials": [],
    "execution_status": "running",
}
(OUTPUT / "candidate-compare-partial.json").write_text(
    json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
for case in report["cases"]:
    for repeat in (1, 2):
        payload = {"model": MODEL,
            "messages": [{"role": "system", "content": case["system"]},
                         {"role": "user", "content": case["user"]}],
            "stream": False, "keep_alive": "5m",
            "options": {"temperature": 0.1, "num_predict": 512,
                "repeat_penalty": 1.25, "repeat_last_n": 64, "num_ctx": 4096}}
        encoded = json.dumps(payload, ensure_ascii=False,
                             separators=(",", ":")).encode()
        trial = {"case_id": case["id"], "repeat": repeat, "budget": 512,
            "request_sha256": hashlib.sha256(encoded).hexdigest(),
            "started_at_utc": datetime.now(timezone.utc).isoformat()}
        start = time.monotonic()
        try:
            result = post("/api/chat", payload, timeout=65)
            message = result.get("message") if isinstance(result.get("message"), dict) else {}
            content = message.get("content") if isinstance(message.get("content"), str) else ""
            thinking = message.get("thinking") if isinstance(message.get("thinking"), str) else ""
            trial.update({"http_status": 200, "model_returned": result.get("model"),
                "done": result.get("done"), "done_reason": result.get("done_reason"),
                "eval_count": result.get("eval_count"),
                "prompt_eval_count": result.get("prompt_eval_count"),
                "content_chars": len(content),
                "content_sha256": hashlib.sha256(content.encode()).hexdigest(),
                "content": content, "thinking_chars": len(thinking),
                "thinking_sha256": hashlib.sha256(thinking.encode()).hexdigest(),
                "raw_thinking_saved": False,
                "total_duration_ns": result.get("total_duration"),
                "load_duration_ns": result.get("load_duration")})
        except Exception as exc:
            trial.update({"error_type": type(exc).__name__,
                "error_category": "timeout" if isinstance(exc, TimeoutError) else "transport_or_api_error"})
        trial["elapsed_seconds"] = round(time.monotonic() - start, 3)
        report["trials"].append(trial)
        (OUTPUT / "candidate-compare-partial.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(json.dumps({key: trial.get(key) for key in
            ("case_id", "repeat", "http_status", "done_reason", "eval_count",
             "content_chars", "elapsed_seconds", "error_category")}, ensure_ascii=False),
            flush=True)
report["execution_status"] = "completed" if len(report["trials"]) == 4 else "execution_failed"
report["completed_at_utc"] = datetime.now(timezone.utc).isoformat()
(OUTPUT / "candidate-compare-report.json").write_text(
    json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print("FINAL", json.dumps({"trials": len(report["trials"]),
    "execution_status": report["execution_status"], "digest": report["model_digest"]}))
if report["execution_status"] != "completed":
    raise SystemExit(1)
