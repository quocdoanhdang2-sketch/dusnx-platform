"""HTTP contract regressions with entities unrelated to the observed cloud case."""
import json
from io import BytesIO
import urllib.error
import pytest
from test_week2_acceptance import isolated_week2_env, client, _register_and_login
from apps.ai_api import provider


def test_both_topics_does_not_select_a_third_unrelated_memory():
    from apps.ai_api.grounding import memory_answer_with_selection
    memories=[{"content":"Chọn Penpot cho công cụ thiết kế","memory_id":"design"},
              {"content":"Chọn trà sen cho đồ uống","memory_id":"drink"},
              {"content":"Lịch phát hành vào thứ sáu","memory_id":"release"}]
    answer,selected=memory_answer_with_selection("Cả hai công cụ thiết kế và đồ uống đang dùng gì?",memories)
    assert {m["memory_id"] for m in selected}=={"design","drink"}
    assert "thứ sáu" not in answer


def setup_user(client,name):
    _,token=_register_and_login(client,name)
    h={"Authorization":f"Bearer {token}"}
    sid=client.post("/v1/sessions",headers=h,json={"title":"Contract test"}).json()["session_id"]
    return h,sid


def send(client,h,sid,message,**kwargs):
    response=client.post("/v1/chat",headers=h,json=dict(session_id=sid,message=message,**kwargs))
    assert response.status_code==200,response.text
    return response.json()


def test_two_topics_summary_ambiguity_supersession_and_isolation(client,monkeypatch):
    import apps.ai_api.main as main
    h,sid=setup_user(client,"provenance_a")
    other,_=setup_user(client,"provenance_b")
    secret=client.post("/v1/memories",headers=other,json={"info_type":"decision","content":"bí mật user khác"}).json()
    first=send(client,h,sid,"Hãy nhớ rằng chúng tôi chọn Figma cho công cụ thiết kế.")["memory_ids_used"][0]
    second=send(client,h,sid,"Hãy nhớ rằng chúng tôi chọn trà sen cho đồ uống buổi họp.")["memory_ids_used"][0]
    send(client,h,sid,"Đổi Figma sang Penpot");send(client,h,sid,"Có")
    active=client.get("/v1/memories",headers=h).json()
    design=next(m["memory_id"] for m in active if "Penpot" in m["content"])
    def forbidden(**kwargs):raise AssertionError("Template must not call provider")
    monkeypatch.setattr(main,"generate_response",forbidden)
    for question,ids,required,excluded in [
        ("Công cụ thiết kế được chọn là gì?",{design},["Penpot"],["trà sen"]),
        ("Đồ uống buổi họp được chọn là gì?",{second},["trà sen"],["Penpot"]),
        ("Công cụ thiết kế và đồ uống buổi họp đang dùng gì?",{design,second},["Penpot","trà sen"],[]),
        ("Quyết định hiện tại của tôi là gì?",set(),["?"],["Penpot","trà sen"]),
    ]:
        r=send(client,h,sid,question)
        assert set(r["candidate_memory_ids"])=={design,second}
        assert set(r["memory_ids_used"])==ids and r["prompt_memory_ids"]==[]
        assert first not in r["candidate_memory_ids"] and secret["memory_id"] not in r["candidate_memory_ids"]
        assert r["provider_called"] is False and r["provider_used"] is None and r["model_used"] is None
        assert r["provider_ok"] is True
        assert r["response_source"]==("grounded_template" if ids else "clarification")
        assert all(x in r["reply"] for x in required)
        assert all(x not in r["reply"] for x in excluded+["Figma",".."])


def test_llm_transport_failure_and_retry_preserve_state(client,monkeypatch):
    h,sid=setup_user(client,"transport_retry")
    monkeypatch.setenv("DUSNX_PROVIDER","ollama")
    calls=[]
    def offline(request,timeout):
        calls.append(request.full_url)
        raise urllib.error.URLError("test unavailable")
    monkeypatch.setattr(provider.urllib.request,"urlopen",offline)
    text="Viết hai câu ngắn về một buổi sáng yên tĩnh."
    failed=send(client,h,sid,text)
    assert failed["provider_called"] and not failed["provider_ok"]
    assert failed["provider_used"]=="ollama" and failed["model_used"] is None
    assert failed["response_source"]=="provider_error" and failed["memory_ids_used"]==[]
    events_before=client.get("/v1/me/events",headers=h).json()["events"]
    def success(request,timeout):
        calls.append(request.full_url)
        return BytesIO(json.dumps({"done":True,"message":{"content":"Buổi sáng yên tĩnh."},"model":"test-llm","eval_count":5}).encode())
    monkeypatch.setattr(provider.urllib.request,"urlopen",success)
    result=send(client,h,sid,text,is_retry=True)
    assert result["provider_called"] and result["provider_ok"] and result["response_source"]=="llm"
    assert result["provider_used"]=="ollama" and result["model_used"]=="test-llm"
    assert result["state_version"]==failed["state_version"]
    assert client.get("/v1/me/events",headers=h).json()["events"]==events_before
    assert len(calls)==2  # One failed native request, then one explicit retry; no silent fallback.


def test_openai_without_configuration_is_not_called(client,monkeypatch):
    h,sid=setup_user(client,"missing_configuration")
    monkeypatch.setenv("DUSNX_PROVIDER","openai");monkeypatch.setattr(provider,"OPENAI_API_KEY","")
    r=send(client,h,sid,"Viết một lời chào ngắn.")
    assert not r["provider_called"] and not r["provider_ok"]
    assert r["provider_used"] is None and r["model_used"] is None


def test_llm_prompt_selection_is_distinct_from_answer_citations(client,monkeypatch):
    h,sid=setup_user(client,"prompt_selection")
    design=client.post("/v1/memories",headers=h,json={"info_type":"decision","content":"Chọn Penpot cho công cụ thiết kế."}).json()
    client.post("/v1/memories",headers=h,json={"info_type":"decision","content":"Chọn trà sen cho đồ uống."})
    monkeypatch.setenv("DUSNX_PROVIDER","ollama");captured=[]
    def transport(request,timeout):
        captured.append(json.loads(request.data))
        return BytesIO(b'{"done":true,"message":{"content":"Generated prose"},"model":"test-model"}')
    monkeypatch.setattr(provider.urllib.request,"urlopen",transport)
    result=send(client,h,sid,"Viết đoạn giới thiệu công cụ thiết kế.")
    system=captured[0]["messages"][0]["content"]
    assert "Penpot" in system and "trà sen" not in system
    assert result["prompt_memory_ids"]==[design["memory_id"]]
    assert result["memory_ids_used"]==[]  # No verified citation from free-form generation.
    assert result["provider_called"] and result["response_source"]=="llm"
