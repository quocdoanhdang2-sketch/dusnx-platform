"""Synthetic Gateway transport/provenance plus language check; no semantic review.

No benchmark input, no credentials/headers/private data in saved evidence.
"""
import argparse
from datetime import datetime,timezone
import json
import os
from pathlib import Path
import secrets
import sys
import httpx
import re

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "scripts"))
sys.path.insert(0, str(REPO_ROOT / "python"))
from apps.ai_api.language import assess_response_language
from verify_bilingual_generation import assess_completion, verify_ollama_model_identity


def assess_generation_provenance(response, expected_model, expected_language="vi"):
    """Separate a completed provider call from application acceptance and task review."""
    attempts = response.get("provider_attempts") or []
    called_attempts = [attempt for attempt in attempts if attempt.get("called", True)]
    attempt_models = [attempt.get("model_used") for attempt in called_attempts]
    actual_model = response.get("model_used") or next(
        (model for model in reversed(attempt_models) if model), None
    )
    transport_ok = bool(
        response.get("provider_called") is True
        and response.get("provider_used") == "ollama"
        and response.get("provider_call_count", 0) >= 1
        and called_attempts
        and all(model == expected_model for model in attempt_models)
    )
    text = response.get("provider_sanitized_reply") or response.get("reply", "")
    language = (assess_response_language(text, expected_language)
                if response.get("provider_ok") is True
                else {"status": "not_applicable", "reason": "provider_not_successful"})
    last_attempt = called_attempts[-1] if called_attempts else {}
    completion = assess_completion(
        text,
        response.get("done_reason") or last_attempt.get("done_reason"),
        response.get("tokens_generated") if response.get("tokens_generated") is not None
        else last_attempt.get("tokens_generated"),
        response.get("token_budget", 512),
        provider_ok=response.get("provider_ok") is True,
    ) if called_attempts else {"status": "not_applicable", "reason": "provider_not_called"}
    if not transport_ok:
        status = "transport_failed_or_model_unverified"
    elif response.get("provider_ok") is not True or response.get("response_source") != "llm":
        status = "provider_quality_rejected"
    elif language["status"] != "matched":
        status = "language_failed"
    elif completion["status"] == "failed":
        status = "completion_failed"
    else:
        status = "transport_and_language_passed_task_unverified"
    return {
        "status": status,
        "transport_status": "passed" if transport_ok else "failed",
        "actual_model": actual_model,
        "language_evaluation": language,
        "language_status": language["status"],
        "completion_evaluation": completion,
        "task_status": "uncertain",
        "task_review": "not_evaluated",
        "application_quality_status": (
            "accepted" if response.get("provider_ok") is True and response.get("response_source") == "llm"
            else "rejected" if response.get("quality_status") == "failed" else "not_successful"
        ),
        "provider_call_count": response.get("provider_call_count", 0),
    }


def verify(base,output,expected_model="qwen2.5:0.5b",expected_model_digest=None):
    report=dict(timestamp_utc=datetime.now(timezone.utc).isoformat(),gateway=base,
                expected_model=expected_model,expected_model_digest=expected_model_digest or "unverified",
                model_identity="unverified",status="unverified",responses={})
    headers={}
    with httpx.Client(base_url=base,timeout=120) as client:
        def call(method,path,**kwargs):
            response=client.request(method,path,headers=headers,**kwargs)
            if response.status_code>=400:raise RuntimeError(f"{method} {path}: HTTP {response.status_code}")
            return response.json()
        def session():return call("POST","/v1/sessions",json={"title":"Synthetic provenance acceptance"})["session_id"]
        def chat(sid,text):return call("POST","/v1/chat",json={"session_id":sid,"message":text})
        def record(name,r):
            fields=("reply","raw_provider_reply","provider_sanitized_reply","candidate_memory_ids","prompt_memory_ids",
                    "memory_ids_used","provider_called","provider_call_count","response_source","provider_ok",
                    "provider_used","model_used","tokens_generated","done_reason","sanitizer_changed",
                    "raw_output_sha256","quality_status","provider_elapsed_ms","provider_attempts","token_budget")
            report["responses"][name]={k:r.get(k) for k in fields}
        try:
            identity=verify_ollama_model_identity(expected_model,expected_model_digest)
            report["model_identity"]=identity
            report["expected_model_digest"]=expected_model_digest or identity["digest"]
            health=call("GET","/v1/health")
            report["health"]={k:health.get(k) for k in ("runtime_mode","checkpoint_loaded","model_version","provider_ok")}
            credentials={"username":"provenance_"+secrets.token_hex(8),"password":secrets.token_urlsafe(24)}
            call("POST","/v1/auth/register",json=credentials)
            token=call("POST","/v1/auth/login",json=credentials)["token"]
            headers["Authorization"]="Bearer "+token
            sid=session()
            old=chat(sid,"Hãy nhớ rằng chúng tôi chọn GCP cho dự án hạ tầng đám mây năm 2026.")["memory_ids_used"][0]
            database=chat(sid,"Hãy nhớ rằng chúng tôi chọn PostgreSQL làm hệ thống cơ sở dữ liệu chính.")["memory_ids_used"][0]
            proposed=chat(sid,"Đổi quyết định hạ tầng đám mây sang AWS nhé")
            assert proposed["next_action"]=="await_confirm"
            updated=chat(sid,"Đồng ý")
            assert updated["intent"]=="decision_update"
            infra=updated["memory_ids_used"][0]
            sid=session()
            questions={"infrastructure":"Hạ tầng đám mây được chọn cho dự án là gì?",
                       "database":"Cơ sở dữ liệu được chọn là gì?",
                       "both":"Hạ tầng đám mây và cơ sở dữ liệu được chọn là gì?",
                       "ambiguous":"Quyết định hiện tại của tôi là gì?"}
            expected={"infrastructure":{infra},"database":{database},"both":{infra,database},"ambiguous":set()}
            for name,text in questions.items():
                r=chat(sid,text);record(name,r)
                assert set(r["candidate_memory_ids"])=={infra,database}
                assert set(r["memory_ids_used"])==expected[name]
                assert not r["provider_called"] and r["provider_used"] is None and r["model_used"] is None
                assert r["provider_ok"] and r["prompt_memory_ids"]==[]
                assert r["response_source"]==("clarification" if name=="ambiguous" else "grounded_template")
                assert "GCP" not in r["reply"] and ".." not in r["reply"]
                if name=="infrastructure":assert "AWS" in r["reply"] and "PostgreSQL" not in r["reply"]
                if name=="database":assert "PostgreSQL" in r["reply"] and "AWS" not in r["reply"]
                if name=="both":assert "PostgreSQL" in r["reply"] and "AWS" in r["reply"]
                if name=="ambiguous":assert "?" in r["reply"]
            memories=call("GET","/v1/memories?include_inactive=true")
            assert any(m["memory_id"]==old and not m["is_active"] for m in memories)
            generated=chat(session(),"Viết hai câu về lợi ích của việc đọc sách.");record("llm",generated)
            generation_evaluation = assess_generation_provenance(generated, expected_model, "vi")
            report["generation_evaluation"] = generation_evaluation
            report["transport_status"] = generation_evaluation["transport_status"]
            report["language_status"] = generation_evaluation["language_status"]
            report["completion_status"] = generation_evaluation["completion_evaluation"]["status"]
            report["task_status"] = generation_evaluation["task_status"]
            report["status"] = generation_evaluation["status"]
        except Exception as exc:
            report["error"]=type(exc).__name__  # never serialize requests/auth bodies
        finally:
            if headers:
                try:call("POST","/v1/auth/logout")
                except Exception:report["logout"]="failed"
    path=Path(output);path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    print(json.dumps(report,ensure_ascii=False,indent=2))
    return 0 if report["status"]=="transport_and_language_passed_task_unverified" else 1


def provenance_stack_directory(output):
    output_path = Path(output).resolve()
    return output_path.parent / f"{output_path.stem}-stack"


if __name__=="__main__":
    if hasattr(sys.stdout,"reconfigure"):sys.stdout.reconfigure(encoding="utf-8")
    p=argparse.ArgumentParser()
    p.add_argument("--gateway",default=None,help="Gateway URL to test against")
    p.add_argument("--spawn-stack",action="store_true",help="Spawn an isolated local Stack automatically")
    p.add_argument("--output",default="runtime/chat-provenance.json")
    p.add_argument("--expected-model",default=os.getenv("DUSNX_EXPECTED_MODEL","qwen2.5:0.5b"),
                   help="Exact Ollama model name expected in generation provenance")
    p.add_argument("--expected-model-digest",default=os.getenv("DUSNX_EXPECTED_MODEL_DIGEST"),
                   help="Expected immutable digest from Ollama /api/tags")
    a=p.parse_args()
    if a.spawn_stack or not a.gateway:
        from verify_week4_runtime import Stack
        stack_dir = provenance_stack_directory(a.output)
        old_capture = os.environ.get("DUSNX_CAPTURE_RAW_GENERATION")
        os.environ["DUSNX_CAPTURE_RAW_GENERATION"] = "1"
        try:
            with Stack(stack_dir,DUSNX_OLLAMA_MODEL=a.expected_model) as stack:
                sys.exit(verify(stack.url, a.output,a.expected_model,a.expected_model_digest))
        finally:
            if old_capture is None:os.environ.pop("DUSNX_CAPTURE_RAW_GENERATION",None)
            else:os.environ["DUSNX_CAPTURE_RAW_GENERATION"]=old_capture
    else:
        sys.exit(verify(a.gateway,a.output,a.expected_model,a.expected_model_digest))
