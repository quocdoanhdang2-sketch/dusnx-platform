"""Real Gateway acceptance: synthetic account, two topics, one actual LLM call.

No benchmark input, no credentials/headers/private data in saved evidence.
"""
import argparse
from datetime import datetime,timezone
import json
from pathlib import Path
import secrets
import sys
import httpx


def verify(base,output):
    report=dict(timestamp_utc=datetime.now(timezone.utc).isoformat(),gateway=base,status="unverified",responses={})
    headers={}
    with httpx.Client(base_url=base,timeout=120) as client:
        def call(method,path,**kwargs):
            response=client.request(method,path,headers=headers,**kwargs)
            if response.status_code>=400:raise RuntimeError(f"{method} {path}: HTTP {response.status_code}")
            return response.json()
        def session():return call("POST","/v1/sessions",json={"title":"Synthetic provenance acceptance"})["session_id"]
        def chat(sid,text):return call("POST","/v1/chat",json={"session_id":sid,"message":text})
        def record(name,r):
            fields=("reply","candidate_memory_ids","prompt_memory_ids","memory_ids_used","provider_called",
                    "response_source","provider_ok","provider_used","model_used","tokens_generated")
            report["responses"][name]={k:r.get(k) for k in fields}
        try:
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
            assert generated["provider_called"] and generated["provider_ok"]
            assert generated["response_source"]=="llm" and generated["provider_used"]=="ollama"
            assert generated["model_used"]=="qwen2.5:0.5b"
            report["status"]="passed"
        except Exception as exc:
            report["error"]=type(exc).__name__  # never serialize requests/auth bodies
        finally:
            if headers:
                try:call("POST","/v1/auth/logout")
                except Exception:report["logout"]="failed"
    path=Path(output);path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps(report,ensure_ascii=False,indent=2))
    return 0 if report["status"]=="passed" else 1


if __name__=="__main__":
    if hasattr(sys.stdout,"reconfigure"):sys.stdout.reconfigure(encoding="utf-8")
    p=argparse.ArgumentParser();p.add_argument("--gateway",default="http://127.0.0.1:8080")
    p.add_argument("--output",default="runtime/chat-provenance.json");a=p.parse_args()
    sys.exit(verify(a.gateway,a.output))
