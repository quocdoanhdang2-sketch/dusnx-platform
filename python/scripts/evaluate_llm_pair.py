"""Paired LLM-only Gateway evaluation. No retrieval/templates/router predictions."""
import argparse
import csv
import getpass
import hashlib
import json
from pathlib import Path
import random
import statistics
import time
import uuid
import urllib.request
from dusnx_core.llm_data import digest, normalized, read_sft, verify_file_manifest, verify_full_training_gate, write_json

CRITERIA=('vietnamese','grounded','clarification','no_obsolete','no_false_save','final_answer')


def automatic_checks(case,text):
    answer=normalized(text);contract=case['quality_contracts'][-1]
    system=normalized(case['messages'][0]['content'])
    false_save_guard=None
    if 'chưa có kết quả lưu' in system or 'chưa xác nhận lưu' in system:
        affirmative=('đã lưu' in answer or 'đã ghi nhớ' in answer) and not any(marker in answer for marker in ('chưa thể xác nhận đã lưu','không thể xác nhận đã lưu','chưa được lưu'))
        false_save_guard=not affirmative
    return {'required_fact_exact':all(normalized(value) in answer for value in contract['required_facts']),'forbidden_fact_exact':all(normalized(value) not in answer for value in contract['forbidden_facts']),'clarification_shape':contract['response_mode']!='clarify' or '?' in text,'no_false_save_heuristic':false_save_guard}


def promotion(rows,ratings,locked_human_test=False):
    by_id={r['output_id']:r for r in rows}
    if len(by_id)!=len(rows):raise ValueError('Duplicate output ID')
    if len(ratings)!=len(by_id) or {r['output_id'] for r in ratings}!=set(by_id):raise ValueError('Missing/duplicate/unknown review row')
    scores={m:{c:[] for c in CRITERIA} for m in ('base','candidate')}
    failures=[]
    for r in ratings:
        if not r.get('reviewer','').strip() or not r.get('reviewed_at','').strip():raise ValueError('Human reviewer/date required')
        pred=by_id[r['output_id']]
        for c in CRITERIA:
            if str(r[c]) not in ('0','1'):raise ValueError('Rating must explicitly be 0 or 1')
            scores[pred['arm']][c].append(int(r[c]))
        if not pred['provider_ok'] or pred['response_source']!='llm' or not pred['provider_called']:failures.append(pred['output_id'])
    means={m:{c:statistics.mean(v) if v else None for c,v in s.items()} for m,s in scores.items()}
    paired={}
    for r in ratings:paired.setdefault(by_id[r['output_id']]['case_id'],{})[by_id[r['output_id']]['arm']]=r
    regressions=[{'case_id':case,'criterion':c} for case,arms in paired.items() if set(arms)=={'base','candidate'} for c in CRITERIA if int(arms['candidate'][c])<int(arms['base'][c])]
    complete=all(set(v)=={'base','candidate'} for v in paired.values()) and bool(paired)
    passed=complete and locked_human_test and not failures and not regressions and all(means['candidate'][c] is not None and means['candidate'][c]>=means['base'][c] for c in CRITERIA) and means['candidate']['vietnamese']>=.95 and all(means['candidate'][c]==1 for c in ('grounded','clarification','no_obsolete','no_false_save'))
    return dict(promote=passed,scores=means,regressions=regressions,provider_failures=failures,human_test_attested=locked_human_test,note='Small paired test; no statistical superiority claim. Default base is never changed automatically.')


def post(url,payload,token=None):
    headers={'Content-Type':'application/json'}
    if token:headers['Authorization']='Bearer '+token
    req=urllib.request.Request(url,data=json.dumps(payload).encode(),headers=headers)
    with urllib.request.urlopen(req,timeout=180) as r:return json.load(r)


def summarize(rows):
    report={}
    for arm in ('base','candidate'):
        selected=[r for r in rows if r['arm']==arm]
        successful=[r for r in selected if r.get('provider_ok')]
        times=[r['gateway_roundtrip_ms'] for r in successful]
        checks={}
        for criterion in ('required_fact_exact','forbidden_fact_exact','clarification_shape','no_false_save_heuristic'):
            values=[row['automatic'][criterion] for row in successful if row.get('automatic',{}).get(criterion) is not None]
            checks[criterion]={'passed':sum(values),'measured':len(values),'rate':statistics.mean(values) if values else None}
        report[arm]=dict(successful=len(successful),total=len(selected),mean_gateway_roundtrip_ms=statistics.mean(times) if times else None,median_gateway_roundtrip_ms=statistics.median(times) if times else None,automatic_checks=checks)
    return report


def main():
    p=argparse.ArgumentParser();p.add_argument('--gateway',default='http://localhost:8080');p.add_argument('--data',default='datasets/llm_sft');p.add_argument('--base',default='qwen2.5:0.5b');p.add_argument('--candidate',default='dusnx-vi-candidate');p.add_argument('--output',required=True);p.add_argument('--ratings');p.add_argument('--dev-smoke',action='store_true')
    a=p.parse_args();out=Path(a.output)
    if a.ratings:
        run=json.loads((out/'run.json').read_text(encoding='utf-8'))
        predictions=json.loads((out/'raw_outputs.json').read_text(encoding='utf-8'))
        if digest(out/'raw_outputs.json')!=run['outputs_sha256']:raise ValueError('Outputs changed after review package')
        attested=False
        if not run['dev_smoke']:
            data=Path(a.data);lock=json.loads((data/'manifest.json').read_text(encoding='utf-8'))
            verify_file_manifest(data,lock);verify_full_training_gate(data,lock)
            attested=lock['files']['test.jsonl']==run['test_sha256']
        with open(a.ratings,encoding='utf-8-sig',newline='') as f:report=promotion(predictions,list(csv.DictReader(f)),attested)
        write_json(out/'promotion_report.json',report);print(json.dumps(report,ensure_ascii=False));return
    if a.base==a.candidate:raise ValueError('Comparison needs distinct model names')
    if out.exists() and any(out.iterdir()):raise ValueError('Do not overwrite an evaluation; use new directory')
    root=Path(a.data);lock=json.loads((root/'manifest.json').read_text(encoding='utf-8'));verify_file_manifest(root,lock)
    # Development smoke is separate from the frozen test; no test answers are read.
    split='validation' if a.dev_smoke else 'test'
    if not a.dev_smoke:verify_full_training_gate(root,lock)
    cases=read_sft(root/f'{split}.jsonl',split)
    if a.dev_smoke:cases=cases[:2]
    token=getpass.getpass('Gateway Bearer token (hidden; never saved): ')
    rows=[];review=[]
    for case in cases:
        order=[('base',a.base),('candidate',a.candidate)]
        random.Random(case['id']).shuffle(order)
        for arm,model in order:
            start=time.perf_counter()
            try:response=post(a.gateway.rstrip('/')+'/api/v1/llm-evaluation',{'model':model,'messages':case['messages'][:-1]},token)
            except Exception as exc:response=dict(text='',provider_ok=False,provider_called=False,response_source='transport_error',error=type(exc).__name__)
            response['gateway_roundtrip_ms']=(time.perf_counter()-start)*1000
            if response.get('model_used') not in (None,model,model+':latest'):
                response.update(provider_ok=False,error='UnexpectedModel')
            oid=uuid.uuid4().hex[:12]
            rows.append(dict(output_id=oid,case_id=case['id'],arm=arm,requested_model=model,automatic=automatic_checks(case,response.get('text','')),**response))
            review.append(dict(output_id=oid,case_id=case['id'],prompt=json.dumps(case['messages'][:-1],ensure_ascii=False),reference=case['messages'][-1]['content'],answer=response.get('text',''),**{c:'' for c in CRITERIA},reviewer='',reviewed_at='',notes=''))
    write_json(out/'raw_outputs.json',rows)
    write_json(out/'run.json',dict(test_sha256=digest(root/f'{split}.jsonl'),dev_smoke=a.dev_smoke,base=a.base,candidate=a.candidate,outputs_sha256=digest(out/'raw_outputs.json'),test_review_status='pending; explicit human attestation required',sampling={'temperature':0,'seed':20260930,'num_predict':256}))
    with (out/'blind_ratings.csv').open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(review[0]));w.writeheader();w.writerows(review)
    summary=summarize(rows)
    write_json(out/'summary.json',summary)
    write_json(out/'errors.json',[r for r in rows if not r.get('provider_ok')])
    print(json.dumps(summary))


if __name__=='__main__':main()
