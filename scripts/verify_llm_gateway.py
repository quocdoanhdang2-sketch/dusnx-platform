"""Real HTTP development smoke with a disposable synthetic account; no test-set use."""
import argparse
import json
from pathlib import Path
import secrets
import urllib.error
import urllib.request


def verify(gateway,output):
    token=None;report={'gateway':gateway,'purpose':'development_transport_smoke_not_quality_score','status':'unverified','outputs':[]}
    def post(path,payload):
        headers={'Content-Type':'application/json'}
        if token:headers['Authorization']='Bearer '+token
        req=urllib.request.Request(gateway.rstrip('/')+'/api/v1/'+path,data=json.dumps(payload).encode(),headers=headers)
        with urllib.request.urlopen(req,timeout=180) as r:return json.load(r)
    try:
        credentials={'username':'llm_smoke_'+secrets.token_hex(8),'password':secrets.token_urlsafe(24)}
        post('auth/register',credentials);token=post('auth/login',credentials)['token']
        messages=[{'role':'system','content':'Trả lời bằng tiếng Việt. Không tự bịa trí nhớ người dùng.'},{'role':'user','content':'Viết hai câu về lợi ích của việc đi bộ.'}]
        base=post('llm-evaluation',{'model':'qwen2.5:0.5b','messages':messages})
        report['outputs'].append({'requested_model':'qwen2.5:0.5b',**base})
        candidate=post('llm-evaluation',{'model':'dusnx-vi-v1','messages':messages})
        report['outputs'].append({'requested_model':'dusnx-vi-v1',**candidate})
        assert base['provider_called'] and base['provider_ok'] and base['response_source']=='llm'
        assert base['model_used']=='qwen2.5:0.5b'
        report['status']='base_transport_verified'
        report['candidate_status']='available_needs_paired_quality_review' if candidate['provider_ok'] else 'not_available_no_finetuned_artifact'
    except Exception as exc:
        report['error']=type(exc).__name__
        if isinstance(exc,urllib.error.HTTPError):report['http_status']=exc.code
    finally:
        if token:
            try:post('auth/logout',{})
            except Exception:pass
        p=Path(output);p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({k:v for k,v in report.items() if k!='outputs'},ensure_ascii=False))
    return report['status']=='base_transport_verified'


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--gateway',default='http://localhost:8080');p.add_argument('--output',default='runtime/llm-gateway-smoke.json');a=p.parse_args()
    raise SystemExit(0 if verify(a.gateway,a.output) else 1)
