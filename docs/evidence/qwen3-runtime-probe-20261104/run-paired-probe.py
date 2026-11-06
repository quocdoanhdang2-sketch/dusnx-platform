import hashlib,json,subprocess,time,urllib.request
from datetime import datetime,timezone
from pathlib import Path
out=Path('runtime/qwen3-template-probe-20261104')
report={'probe_id':'QWEN3_TEMPLATE_THINK_MODE_PAIRED_R1','created_at_utc':datetime.now(timezone.utc).isoformat(),'transport':'direct Ollama /api/chat; not Gateway/application','ollama_version':'0.40.14','base_model':{'tag':'qwen3:4b','digest':'359d7dd4bcdab3d86b87d73ac27966f4dbb9f5efdfcc75d34a8764a09474fae7'},'candidate_model':{'tag':'dusnx-qwen3-4b-no-think-template-probe-20261104','change':'same base weights, same model parameters, only removes final <think> prompt-template prefix'},'settings':{'temperature':0.1,'repeat_penalty':1.25,'repeat_last_n':64,'num_ctx':4096,'budgets':[512,1024],'api_think_field':'omitted because local /api/show advertises only true'},'cases':[
 {'id':'API_GATEWAY_EN','system':'Answer the user request in one concise sentence in English. Do not include analysis or repeat instructions.','user':'In one concise sentence, explain what an API Gateway does.','expected':'A concise explanation identifying an API Gateway as a client entry point and/or request router to backend services; content must not expose analysis.'},
 {'id':'TRANSLATE_ENTITIES_EN','system':'Translate the user request into English. Preserve exact URLs and KEY=VALUE literals. Do not include analysis.','user':'Translate this sentence to English: Dịch vụ https://service.example.net/v2 dùng biến DUSNX_PORT=8188 để nhận kết nối.','expected':'English translation preserves https://service.example.net/v2 and DUSNX_PORT=8188 and keeps translation task.'},
 {'id':'API_GATEWAY_BENEFIT_VI','system':'Trả lời ngắn gọn bằng tiếng Việt. Không lặp lại hướng dẫn hoặc nêu phân tích.','user':'Nêu một lợi ích cụ thể của API Gateway trong kiến trúc microservices.','expected':'One relevant benefit in Vietnamese, such as centralized routing or shared auth/rate limiting; semantic review remains required.'}
], 'trials':[],'execution_status':'running','review':{'decision':'','reviewer':'','notes':''}}
# Stable order: complete all base-model runs, then template candidate; this avoids hidden request changes.
for model in (report['base_model']['tag'],report['candidate_model']['tag']):
 for case in report['cases']:
  budgets=[512,1024] if case['id']=='API_GATEWAY_EN' else [512]
  for budget in budgets:
   reps=2 if case['id']=='API_GATEWAY_EN' else 1
   for rep in range(1,reps+1):
    trial={'model_tag':model,'case_id':case['id'],'budget':budget,'repeat':rep,'started_at_utc':datetime.now(timezone.utc).isoformat(),'timeout_seconds':65}
    payload={'model':model,'messages':[{'role':'system','content':case['system']},{'role':'user','content':case['user']}],'stream':False,'keep_alive':'5m','options':{'temperature':0.1,'num_predict':budget,'repeat_penalty':1.25,'repeat_last_n':64,'num_ctx':4096}}
    raw_req=json.dumps(payload,ensure_ascii=False,separators=(',',':')).encode()
    trial['request_sha256']=hashlib.sha256(raw_req).hexdigest()
    req=urllib.request.Request('http://127.0.0.1:11434/api/chat',data=raw_req,headers={'Content-Type':'application/json'},method='POST')
    start=time.monotonic()
    try:
     with urllib.request.urlopen(req,timeout=65) as response:
      data=json.load(response); trial['http_status']=response.status
     message=data.get('message') if isinstance(data.get('message'),dict) else {}
     content=message.get('content') if isinstance(message.get('content'),str) else ''
     thinking=message.get('thinking') if isinstance(message.get('thinking'),str) else ''
     trial.update({'model_returned':data.get('model'),'done':data.get('done'),'done_reason':data.get('done_reason'),'eval_count':data.get('eval_count'),'prompt_eval_count':data.get('prompt_eval_count'),'total_duration_ns':data.get('total_duration'),'load_duration_ns':data.get('load_duration'),'eval_duration_ns':data.get('eval_duration'),'content_chars':len(content),'content_sha256':hashlib.sha256(content.encode()).hexdigest(),'content':content,'thinking_chars':len(thinking),'thinking_sha256':hashlib.sha256(thinking.encode()).hexdigest(),'raw_thinking_saved':False})
    except Exception as e:
     trial.update({'error_type':type(e).__name__,'error_category':'timeout' if isinstance(e,TimeoutError) else 'transport_or_api_error','http_status':getattr(e,'code',None)})
     report['trials'].append(trial); report['execution_status']='execution_failed'
     (out/'paired-probe-partial.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
     raise
    trial['elapsed_seconds']=round(time.monotonic()-start,3)
    try:
     with urllib.request.urlopen('http://127.0.0.1:11434/api/ps',timeout=3) as r: ps=json.load(r)
     trial['loaded_models']=[{'name':m.get('name'),'size_vram':m.get('size_vram'),'context_length':m.get('context_length')} for m in ps.get('models',[])]
    except Exception as e: trial['resource_probe_error']=type(e).__name__
    report['trials'].append(trial)
    (out/'paired-probe-partial.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({k:trial.get(k) for k in ('model_tag','case_id','budget','repeat','http_status','done_reason','eval_count','content_chars','thinking_chars','elapsed_seconds','load_duration_ns','loaded_models')},ensure_ascii=False),flush=True)
report['execution_status']='completed'; report['completed_at_utc']=datetime.now(timezone.utc).isoformat()
(out/'paired-probe-report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print('FINAL '+json.dumps({'trials':len(report['trials']),'execution_status':report['execution_status'],'output':str(out/'paired-probe-report.json')}),flush=True)
