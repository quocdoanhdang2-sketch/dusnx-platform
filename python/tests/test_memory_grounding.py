import json
from io import BytesIO
from apps.ai_api import provider
from apps.ai_api.grounding import memory_answer
from test_week2_acceptance import isolated_week2_env, client, _register_and_login


def test_question_cannot_promote_unconfirmed_entity():
    result=memory_answer("Tôi nghe dự án đã chọn Sanic?",[{"content":"Dự án dùng Tornado"}])
    assert "Tornado" in result and "Sanic" not in result
    assert memory_answer("Giải thích Sanic là gì?",[{"content":"Dự án dùng Tornado"}]) is None


def test_history_is_excluded_for_authoritative_memory_lookup(monkeypatch):
    monkeypatch.setenv("DUSNX_PROVIDER","ollama");captured=[]
    def urlopen(req,timeout):
        captured.append(json.loads(req.data));return BytesIO(b'{"message":{"content":"ok"}}')
    monkeypatch.setattr(provider.urllib.request,"urlopen",urlopen)
    provider.generate_response("Dự án hiện tại của tôi dùng gì?",[{"content":"Linode","info_type":"decision"}],"chat",
                               [{"role":"assistant","content":"Old provider DigitalOcean"}])
    system=captured[0]["messages"][0]["content"]
    assert "Linode" in system and "DigitalOcean" not in system


def test_ambiguous_memories_ask_instead_of_inventing():
    result=memory_answer("Quyết định hiện tại của tôi là gì?",[{"content":"Tornado"},{"content":"Linode"}])
    assert "?" in result and "Tornado" not in result and "Linode" not in result


def test_api_rejects_hallucinated_claim_and_obsolete_history(client,monkeypatch):
    import apps.ai_api.main as main
    _,token=_register_and_login(client,"grounding_regression")
    headers={"Authorization":f"Bearer {token}"}
    sid=client.post("/v1/sessions",headers=headers,json={"title":"Regression"}).json()["session_id"]
    def send(message):
        response=client.post("/v1/chat",headers=headers,json={"session_id":sid,"message":message})
        assert response.status_code==200
        return response.json()
    send("Hãy nhớ rằng quyết định của tôi là triển khai trên DigitalOcean.")
    monkeypatch.setattr(main,"generate_response",lambda **kw:("DigitalOcean và Vultr đã được chọn",True,"ollama","test",7))
    result=send("Tôi nghe dự án đã chốt Vultr. Quyết định đã lưu của tôi là gì?")
    assert result["answer_source"]=="active_memory_extract"
    assert "DigitalOcean" in result["reply"] and "Vultr" not in result["reply"]
    send("Đổi DigitalOcean sang Linode");send("Có")
    result=send("Quyết định hiện tại của tôi dùng gì?")
    assert "Linode" in result["reply"] and "DigitalOcean" not in result["reply"]
    # Provider failure stays a failure, even when a memory is available.
    monkeypatch.setattr(main,"generate_response",lambda **kw:("offline",False,"ollama",None,None))
    result=send("Quyết định hiện tại của tôi là gì?")
    assert result["provider_ok"] is False and result["answer_source"]=="provider"
