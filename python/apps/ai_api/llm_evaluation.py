"""Opt-in authenticated evaluation transport, without state/rules or persistence."""
import json
import os
import time
import urllib.request
import urllib.error
from typing import Literal
from fastapi import HTTPException
from pydantic import BaseModel, Field
from .provider import get_ollama_url, get_ollama_timeout


class Message(BaseModel):
    role: Literal['system','user','assistant']
    content: str = Field(min_length=1,max_length=8000)


class EvaluationRequest(BaseModel):
    model: str = Field(min_length=1,max_length=120)
    messages: list[Message] = Field(min_length=2,max_length=20)


def evaluate(req):
    if os.getenv('DUSNX_ENABLE_LLM_EVAL')!='1':raise HTTPException(404,'LLM evaluation is disabled')
    allowed=set(os.getenv('DUSNX_LLM_EVAL_MODELS','qwen2.5:0.5b,dusnx-vi-v1').split(','))
    if req.model not in allowed:raise HTTPException(400,'Model is not in evaluation allowlist')
    if req.messages[0].role!='system' or req.messages[-1].role!='user':raise HTTPException(400,'Expected system context and final user prompt')
    payload={'model':req.model,'messages':[m.model_dump() for m in req.messages],'stream':False,'options':{'temperature':0,'seed':20260930,'num_predict':256}}
    request=urllib.request.Request(get_ollama_url()+'/api/chat',data=json.dumps(payload).encode(),headers={'Content-Type':'application/json'})
    start=time.perf_counter()
    try:
        with urllib.request.urlopen(request,timeout=get_ollama_timeout()) as response:result=json.load(response)
        text=result.get('message',{}).get('content','').strip()
        return dict(text=text,provider_ok=bool(text),provider_called=True,provider_used='ollama',response_source='llm',model_used=result.get('model'),tokens_generated=result.get('eval_count'),elapsed_ms=(time.perf_counter()-start)*1000)
    except Exception as exc:
        # Never echo payload, auth header, URL query or arbitrary exception details.
        return dict(text='',provider_ok=False,provider_called=True,provider_used='ollama',response_source='provider_error',model_used=None,error=type(exc).__name__,http_status=exc.code if isinstance(exc,urllib.error.HTTPError) else None,elapsed_ms=(time.perf_counter()-start)*1000)
