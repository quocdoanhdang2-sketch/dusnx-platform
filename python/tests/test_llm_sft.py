import hashlib
import ast
import csv
import copy
import importlib.util
import json
from pathlib import Path
import shutil
import sys
import zipfile
import pytest
from dusnx_core.llm_data import audit, completion_rows, digest, read_sft, validate, verify_file_manifest, verify_full_training_gate
from dusnx_core.llm_artifacts import pack, unpack
from dusnx_core.llm_review import apply_package, export_package

ROOT=Path(__file__).resolve().parents[2]
DATA=ROOT/'datasets/llm_sft'


def partitions():return {s:read_sft(DATA/f'{s}.jsonl',s) for s in ('train','validation','test')}


def test_data_lock_and_split():
    p=partitions();report=audit(p)
    assert report['train']['assistant_pairs']>0
    assert all(report[s]['duplicate_prompt_rate']==0 for s in ('train','validation','test'))
    assert verify_file_manifest(DATA,json.loads((DATA/'manifest.json').read_text()))
    assert all(r['review_status']=='human_reviewed' for s in ('train','validation') for r in p[s])
    assert all(r['review_status']=='human_reviewed' for r in p['test'])
    assert report['quality']['human_review_complete'] is True


def test_known_content_regressions_are_grounded():
    rows={row['id']:row for row in partitions()['train']}
    assert rows['train-006']['messages'][2]['content']=='Mình sẽ trả lời ngắn, tối đa hai ý.'
    assert 'state đã xác nhận' in rows['train-017']['messages'][0]['content']
    assert 'chưa đi qua luồng ghi cơ sở dữ liệu' in rows['train-020']['messages'][0]['content']
    assert all(fact in rows['train-025']['messages'][0]['content'] for fact in rows['train-025']['quality_contracts'][0]['required_facts'])


@pytest.mark.parametrize('field',['id','sequence_id','user_id','scenario_family'])
def test_cross_split_leaks_rejected(field):
    p=partitions();p['validation'][0][field]=p['train'][0][field]
    with pytest.raises(ValueError,match='leakage'):audit(p)


def test_prefix_duplicate_not_hidden_by_different_final_turn():
    p=partitions();c=next(r for r in p['train'] if len(r['messages'])==3)
    p['validation'][0]['messages']=copy.deepcopy(c['messages'])
    p['validation'][0]['quality_contracts']=copy.deepcopy(c['quality_contracts'])
    with pytest.raises(ValueError,match='prompt'):audit(p)


def test_near_duplicate_across_splits_rejected():
    p=partitions();source=next(r for r in p['train'] if r['scenario_family']=='ambiguous_export_request')
    target=p['validation'][0]
    target['messages']=copy.deepcopy(source['messages'])
    target['messages'][1]['content'] += ' nhé'
    target['quality_contracts']=copy.deepcopy(source['quality_contracts'])
    with pytest.raises(ValueError,match='near duplicate'):audit(p)


def test_no_future_in_completion():
    r=next(r for r in partitions()['train'] if len(r['messages'])>3)
    pairs=completion_rows([r])
    assert pairs[0]['prompt']==r['messages'][:2]
    assert pairs[0]['completion']==[r['messages'][2]]
    assert r['messages'][3] not in pairs[0]['prompt']


@pytest.mark.parametrize('fault',['missing_source','missing_license','missing_generation','pii','source','future_label','duplicate'])
def test_invalid_data_rejected(fault):
    p=partitions();r=p['train'][0]
    if fault=='missing_source':del r['source']
    elif fault=='missing_license':del r['license']
    elif fault=='missing_generation':del r['generation_method']
    elif fault=='pii':r['messages'][1]['content']='Email: fictional@example.com'
    elif fault=='source':r['source']='massive_pending'
    elif fault=='future_label':r['expected_future_answer']='leak'
    else:p['train'].append(copy.deepcopy(r))
    with pytest.raises(ValueError):audit(p)


def test_obsolete_fact_in_completion_rejected():
    row=copy.deepcopy(next(r for r in partitions()['train'] if r['scenario_family']=='confirmed_layout_replacement'))
    row['messages'][-1]['content'] += ' Bố cục một cột cũng được dùng.'
    with pytest.raises(ValueError,match='obsolete/rejected fact'):validate([row],'train')


def test_required_fact_not_in_prior_context_rejected():
    row=copy.deepcopy(next(r for r in partitions()['train'] if r['scenario_family']=='cross_session_database'))
    row['quality_contracts'][0]['required_facts']=['Oracle']
    row['messages'][-1]['content']='Dự án Vườn đang dùng Oracle.'
    with pytest.raises(ValueError,match='unsupported'):validate([row],'train')


def test_future_fact_in_earlier_completion_rejected():
    row=copy.deepcopy(next(r for r in partitions()['train'] if r['scenario_family']=='future_fact_guard'))
    row['messages'][2]['content']='Kế hoạch là đi tàu. Bạn muốn bổ sung gì?'
    with pytest.raises(ValueError,match='future fact leaked'):validate([row],'train')


def test_token_length_rejects_completion_truncation():
    class TooLongTokenizer:
        def apply_chat_template(self,messages,tokenize=True):return list(range(513))
    with pytest.raises(ValueError,match='would be truncated'):audit({'train':partitions()['train']},tokenizer=TooLongTokenizer(),max_length=512)


def test_protected_paths_fail_before_read(tmp_path):
    with pytest.raises(ValueError,match='Protected'):read_sft(tmp_path/'holdout_v3_DO_NOT_READ.jsonl','train')


def test_locked_manifest_can_start_full_training():
    manifest=json.loads((DATA/'manifest.json').read_text(encoding='utf-8'))
    verify_full_training_gate(DATA,manifest)


def test_same_person_cannot_author_and_review_test(tmp_path):
    manifest={'status':'human_attested_locked_before_training','files':{'test.jsonl':'abc'}}
    attestation={'human_author':'reviewer-a','reviewer':'reviewer-a','training_reviewed':True,'locked_before_training':True,'test_sha256':'abc'}
    (tmp_path/'human_test_attestation.json').write_text(json.dumps(attestation),encoding='utf-8')
    with pytest.raises(ValueError,match='independent'):verify_full_training_gate(tmp_path,manifest)


def test_lock_command_rejects_same_author_and_reviewer(monkeypatch):
    script=ROOT/'python/scripts/lock_llm_data.py'
    spec=importlib.util.spec_from_file_location('lock_llm_data_for_test',script)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    monkeypatch.setattr(sys,'argv',['lock_llm_data.py','--human-author','person-a','--reviewer','person-a','--train-review-receipt','missing-train.json','--test-review-receipt','missing-test.json','--attest-authored-reviewed-before-predictions'])
    with pytest.raises(ValueError,match='different people'):module.main()


def _copy_sft(tmp_path):
    target=tmp_path/'sft';shutil.copytree(DATA,target);return target


def _complete_review_csv(path,reviewer='test-only-reviewer',timestamp='2026-09-30T10:00:00+07:00'):
    with path.open(encoding='utf-8-sig',newline='') as handle:rows=list(csv.DictReader(handle))
    for row in rows:row.update(decision='approve',reviewer=reviewer,reviewed_at=timestamp)
    with path.open('w',encoding='utf-8-sig',newline='') as handle:
        writer=csv.DictWriter(handle,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)
    return rows


def test_review_package_round_trip_and_receipt_is_test_only(tmp_path):
    data=_copy_sft(tmp_path);package=tmp_path/'package'
    assert export_package(data,package,('train','validation'))==61
    assert 'train:train-001:1' in (package/'review.md').read_text(encoding='utf-8')
    _complete_review_csv(package/'review.csv')
    receipt=apply_package(data,package,allow_test_identities=True)
    assert receipt['test_only'] is True and receipt['row_count']==61
    assert all(row['review_status']=='human_reviewed' for split in ('train','validation') for row in read_sft(data/f'{split}.jsonl',split))
    assert json.loads((data/'manifest.json').read_text())['status']=='human_review_complete_pending_lock'


def test_review_package_rejects_missing_duplicate_stale_and_bad_timestamp(tmp_path):
    data=_copy_sft(tmp_path);package=tmp_path/'package';export_package(data,package,('train','validation'))
    rows=_complete_review_csv(package/'review.csv')
    rows.pop()
    with (package/'review.csv').open('w',encoding='utf-8-sig',newline='') as handle:
        writer=csv.DictWriter(handle,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)
    with pytest.raises(ValueError,match='Missing'):apply_package(data,package,allow_test_identities=True)
    export2=tmp_path/'package2';export_package(data,export2,('train','validation'));rows=_complete_review_csv(export2/'review.csv')
    duplicated=rows+[copy.deepcopy(rows[0])]
    with (export2/'review.csv').open('w',encoding='utf-8-sig',newline='') as handle:
        writer=csv.DictWriter(handle,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(duplicated)
    with pytest.raises(ValueError,match='Duplicate'):apply_package(data,export2,allow_test_identities=True)
    rows[0]['reviewed_at']='2026-09-30'
    with (export2/'review.csv').open('w',encoding='utf-8-sig',newline='') as handle:
        writer=csv.DictWriter(handle,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)
    with pytest.raises(ValueError,match='timezone'):apply_package(data,export2,allow_test_identities=True)
    (data/'train.jsonl').write_text((data/'train.jsonl').read_text(encoding='utf-8')+'\n',encoding='utf-8')
    with pytest.raises(ValueError,match='changed'):apply_package(data,export2,allow_test_identities=True)


def test_ai_draft_cannot_be_exported_as_independent_test(tmp_path):
    data=_copy_sft(tmp_path)
    records=read_sft(data/'test.jsonl','test')
    for row in records:
        row['source']='synthetic_designed'
        row['generation_method']='AI-generated'
    (data/'test.jsonl').write_text(''.join(json.dumps(r,ensure_ascii=False)+'\n' for r in records),encoding='utf-8')
    with pytest.raises(ValueError,match='Replace the AI draft with genuinely human-authored test records first'):
        export_package(data,tmp_path/'test-package',('test',),'human-author-a','2026-09-30T10:00:00+07:00')


def test_test_export_rejects_already_reviewed_records(tmp_path):
    data=_copy_sft(tmp_path)
    records=read_sft(data/'test.jsonl','test')
    records[0]['review_status']='human_reviewed'
    (data/'test.jsonl').write_text(''.join(json.dumps(r,ensure_ascii=False)+'\n' for r in records),encoding='utf-8')
    with pytest.raises(ValueError,match='pending human review'):
        export_package(data,tmp_path/'test-package',('test',),'human-author-a','2026-09-30T10:00:00+07:00')


def test_independent_test_requires_independent_reviewer_and_full_adjudication(tmp_path):
    data=_copy_sft(tmp_path);package=tmp_path/'package'
    test_path=data/'test.jsonl'
    test_rows=[json.loads(line) for line in test_path.read_text(encoding='utf-8').splitlines() if line.strip()]
    for row in test_rows:
        row['review_status']='needs_human_review'
    test_path.write_text(
        ''.join(json.dumps(row,ensure_ascii=False,separators=(',',':'))+'\n' for row in test_rows),
        encoding='utf-8',newline='\n',
    )
    manifest_path=data/'manifest.json'
    manifest=json.loads(manifest_path.read_text(encoding='utf-8'))
    manifest['status']='partial_human_review_pending'
    manifest['files']['test.jsonl']=hashlib.sha256(test_path.read_bytes()).hexdigest()
    manifest_path.write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n',encoding='utf-8',newline='\n')
    export_package(data,package,('test',),'human-author-a','2026-09-30T10:00:00+07:00')
    rows=_complete_review_csv(package/'review.csv',reviewer='human-author-a')
    with pytest.raises(ValueError,match='must differ from its human author'):
        apply_package(data,package,allow_test_identities=True)
    rows[0]['decision']=''
    with (package/'review.csv').open('w',encoding='utf-8-sig',newline='') as handle:
        writer=csv.DictWriter(handle,fieldnames=list(rows[0]))
        writer.writeheader();writer.writerows(rows)
    with pytest.raises(ValueError,match='decision=approve or revise'):
        apply_package(data,package,allow_test_identities=True)


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
        assert body['model']=='dusnx-vi-candidate' and body['options']['temperature']==0
        return io.BytesIO(json.dumps({'done':True,'model':'dusnx-vi-candidate','message':{'content':'Xin chào'},'eval_count':4}).encode())
    monkeypatch.setattr('urllib.request.urlopen',call)
    r=evaluate(EvaluationRequest(model='dusnx-vi-candidate',messages=[{'role':'system','content':'Tiếng Việt'},{'role':'user','content':'Chào'}]))
    assert r['response_source']=='llm' and r['provider_called'] and r['provider_ok']
    assert r['model_used']=='dusnx-vi-candidate'


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
    case=next(row for row in partitions()['validation'] if row['id']=='validation-004')
    checks=mod.automatic_checks(case,'Bìa nên dùng màu xanh lá.')
    assert checks['required_fact_exact'] and checks['forbidden_fact_exact']


def test_eval_api_requires_auth(monkeypatch):
    from apps.ai_api.main import app
    from fastapi.testclient import TestClient
    monkeypatch.setenv('DUSNX_ENABLE_LLM_EVAL','1')
    response=TestClient(app).post('/v1/llm-evaluation',json={'model':'qwen2.5:0.5b','messages':[{'role':'system','content':'test'},{'role':'user','content':'hello'}]})
    assert response.status_code==401
