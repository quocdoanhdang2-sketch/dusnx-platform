import ast
import copy
import importlib.util
import json
from pathlib import Path
import zipfile
import pytest
from dusnx_core.llm_data import audit, completion_rows, digest, read_sft, verify_file_manifest
from dusnx_core.llm_artifacts import pack, unpack

ROOT=Path(__file__).resolve().parents[2]
DATA=ROOT/'datasets/llm_sft'


def partitions():return {s:read_sft(DATA/f'{s}.jsonl',s) for s in ('train','validation','test')}


def test_data_lock_and_split():
    p=partitions();report=audit(p)
    assert report['train']['assistant_pairs']>0
    assert all(r['duplicate_prompt_rate']==0 for r in report.values())
    assert verify_file_manifest(DATA,json.loads((DATA/'manifest.json').read_text()))
    assert all(r['review_status'] in ('ai_authored_pending_human_review','human_reviewed') for rows in p.values() for r in rows)


@pytest.mark.parametrize('field',['id','sequence_id','user_id','scenario_family'])
def test_cross_split_leaks_rejected(field):
    p=partitions();p['validation'][0][field]=p['train'][0][field]
    with pytest.raises(ValueError,match='leakage'):audit(p)


def test_prefix_duplicate_not_hidden_by_different_final_turn():
    p=partitions();c=next(r for r in p['train'] if len(r['messages'])>3)
    p['validation'][0]['messages']=copy.deepcopy(c['messages'][:3])
    p['validation'][0]['messages'][-1]['content']='Đáp án khác không được che prompt trùng.'
    with pytest.raises(ValueError,match='prompt'):audit(p)


def test_no_future_in_completion():
    r=next(r for r in partitions()['train'] if len(r['messages'])>3)
    pairs=completion_rows([r])
    assert pairs[0]['prompt']==r['messages'][:2]
    assert pairs[0]['completion']==[r['messages'][2]]
    assert r['messages'][3] not in pairs[0]['prompt']


@pytest.mark.parametrize('fault',['missing','pii','source','future','duplicate'])
def test_invalid_data_rejected(fault):
    p=partitions();r=p['train'][0]
    if fault=='missing':del r['source_revision']
    elif fault=='pii':r['messages'][1]['content']='Email: fictional@example.com'
    elif fault=='source':r['source']='massive_pending'
    elif fault=='future':r['expected_future_answer']='leak'
    else:p['train'].append(copy.deepcopy(r))
    with pytest.raises(ValueError):audit(p)


def test_protected_paths_fail_before_read(tmp_path):
    with pytest.raises(ValueError,match='Protected'):read_sft(tmp_path/'holdout_v3_DO_NOT_READ.jsonl','train')


def test_artifact_tamper_and_traversal(tmp_path):
    root=tmp_path/'run';root.mkdir();(root/'adapter.txt').write_text('weights placeholder')
    archive=tmp_path/'run.zip';pack(root,archive)
    unpack(archive,tmp_path/'restored',digest(archive))
    (root/'adapter.txt').write_text('tampered')
    with pytest.raises(ValueError,match='checksum'):verify_file_manifest(root,json.loads((root/'artifact_manifest.json').read_text()))
    bad=tmp_path/'bad.zip'
    with zipfile.ZipFile(bad,'w') as z:z.writestr('../escape','bad')
    with pytest.raises(ValueError,match='Unsafe'):unpack(bad,tmp_path/'bad',digest(bad))
    with pytest.raises(ValueError,match='checksum'):unpack(archive,tmp_path/'wrong','0'*64)


def test_notebook_cells_parse_and_have_no_outputs():
    nb=json.loads((ROOT/'notebooks/finetune_llm_colab.ipynb').read_text(encoding='utf-8'))
    for c in nb['cells']:
        if c['cell_type']=='code':
            ast.parse(''.join(c['source']))
            assert c['outputs']==[] and c['execution_count'] is None


def test_model_override_requires_opt_in_and_allowlist(monkeypatch):
    from apps.ai_api.llm_evaluation import EvaluationRequest,evaluate
    from fastapi import HTTPException
    req=EvaluationRequest(model='rogue',messages=[{'role':'system','content':'test'},{'role':'user','content':'hello'}])
    monkeypatch.delenv('DUSNX_ENABLE_LLM_EVAL',raising=False)
    with pytest.raises(HTTPException) as e:evaluate(req)
    assert e.value.status_code==404
    monkeypatch.setenv('DUSNX_ENABLE_LLM_EVAL','1')
    with pytest.raises(HTTPException) as e:evaluate(req)
    assert e.value.status_code==400


def test_eval_transport_is_real_llm_not_template(monkeypatch):
    import io
    from apps.ai_api.llm_evaluation import EvaluationRequest,evaluate
    monkeypatch.setenv('DUSNX_ENABLE_LLM_EVAL','1')
    def call(req,timeout):
        body=json.loads(req.data)
        assert body['model']=='dusnx-vi-v1' and body['options']['temperature']==0
        return io.BytesIO(json.dumps({'model':'dusnx-vi-v1','message':{'content':'Xin chào'},'eval_count':4}).encode())
    monkeypatch.setattr('urllib.request.urlopen',call)
    r=evaluate(EvaluationRequest(model='dusnx-vi-v1',messages=[{'role':'system','content':'Tiếng Việt'},{'role':'user','content':'Chào'}]))
    assert r['response_source']=='llm' and r['provider_called'] and r['provider_ok']
    assert r['model_used']=='dusnx-vi-v1'


def test_promotion_rejects_regression_and_missing_human_test():
    spec=importlib.util.spec_from_file_location('pair',ROOT/'python/scripts/evaluate_llm_pair.py');mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
    rows=[dict(output_id=arm,case_id='x',arm=arm,provider_ok=True,provider_called=True,response_source='llm') for arm in ('base','candidate')]
    ratings=[dict(output_id=arm,reviewer='real-reviewer',reviewed_at='2026-09-30',**{c:'1' for c in mod.CRITERIA}) for arm in ('base','candidate')]
    assert not mod.promotion(rows,ratings)['promote']
    assert mod.promotion(rows,ratings,True)['promote']
    ratings[1]['no_obsolete']='0'
    assert not mod.promotion(rows,ratings,True)['promote']
    with pytest.raises(ValueError):mod.promotion(rows,ratings[:1],True)
    timings=[dict(arm='base',provider_ok=True,gateway_roundtrip_ms=20),dict(arm='candidate',provider_ok=False,gateway_roundtrip_ms=1)]
    assert mod.summarize(timings)['candidate']['mean_gateway_roundtrip_ms'] is None


def test_eval_api_requires_auth(monkeypatch):
    from apps.ai_api.main import app
    from fastapi.testclient import TestClient
    monkeypatch.setenv('DUSNX_ENABLE_LLM_EVAL','1')
    response=TestClient(app).post('/v1/llm-evaluation',json={'model':'qwen2.5:0.5b','messages':[{'role':'system','content':'test'},{'role':'user','content':'hello'}]})
    assert response.status_code==401
