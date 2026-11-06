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
from dusnx_core.llm_review import FIELDS, apply_package, export_package

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


def test_english_response_language_accepts_confirmed_timeout_wording():
    row={
        'id':'english-timeout-language-regression',
        'source':'synthetic_designed',
        'source_revision':'validator-regression-fixture',
        'license':'CC0-1.0',
        'generation_method':'AI-generated',
        'scenario_family':'train_technical_code_switch',
        'sequence_id':'english-timeout-language-regression-sequence',
        'user_id':'fictional-language-regression',
        'split':'train',
        'review_status':'needs_human_review',
        'data_kind':'designed_conversation',
        'messages':[
            {'role':'system','content':'Use only confirmed facts.'},
            {'role':'user','content':'The GCP API returned a timeout; explain briefly in English without claiming success.'},
            {'role':'assistant','content':'The GCP API returned a timeout, so the operation cannot be confirmed as successful.'},
        ],
        'quality_contracts':[{
            'assistant_turn':1,'response_mode':'answer','language':'en','response_language':'en',
            'required_facts':['GCP'],'forbidden_facts':[],'future_facts':[],
            'criteria':['grounded','language_compliance'],
        }],
    }
    validate([row],'train')


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


def test_development_manifest_cannot_start_full_training():
    manifest=json.loads((DATA/'manifest.json').read_text(encoding='utf-8'))
    manifest['status']='human_review_complete_pending_lock'
    with pytest.raises(ValueError,match='human-attested'):verify_full_training_gate(DATA,manifest)


def test_same_person_cannot_author_and_review_test(tmp_path):
    manifest=_locked_gate_fixture(tmp_path)
    attestation=json.loads((tmp_path/'human_test_attestation.json').read_text(encoding='utf-8'))
    attestation['human_author']='reviewer-b'
    (tmp_path/'human_test_attestation.json').write_text(json.dumps(attestation),encoding='utf-8')
    with pytest.raises(ValueError,match='independent'):verify_full_training_gate(tmp_path,manifest)


def _locked_gate_fixture(tmp_path):
    files={}
    for name in ('train.jsonl','validation.jsonl','test.jsonl'):
        path=tmp_path/name;path.write_text('{}\n',encoding='utf-8');files[name]=digest(path)
    train_receipt={'schema_version':1,'review_type':'train_validation','test_only':False,'result_files':{'train.jsonl':files['train.jsonl'],'validation.jsonl':files['validation.jsonl']},'row_count':2,'reviewers':['reviewer-b'],'reviewed_at':['2026-10-01T10:00:00+00:00']}
    test_receipt={'schema_version':1,'review_type':'independent_test','test_only':False,'human_author':'author-a','result_files':{'test.jsonl':files['test.jsonl']},'row_count':1,'reviewers':['reviewer-b'],'reviewed_at':['2026-10-01T10:00:00+00:00']}
    for name,receipt in (('train_validation_review_receipt.json',train_receipt),('independent_test_review_receipt.json',test_receipt)):
        path=tmp_path/name;path.write_text(json.dumps(receipt),encoding='utf-8');files[name]=digest(path)
    manifest={'schema_version':4,'status':'human_attested_locked_before_training','locked':True,'row_counts':{'train':1,'validation':1,'test':1},'files':files}
    attestation={'human_author':'author-a','reviewer':'reviewer-b','training_reviewed':True,'locked_before_training':True,'test_sha256':files['test.jsonl'],'train_review_receipt_sha256':files['train_validation_review_receipt.json'],'test_review_receipt_sha256':files['independent_test_review_receipt.json']}
    (tmp_path/'human_test_attestation.json').write_text(json.dumps(attestation),encoding='utf-8')
    return manifest


def _lineaged_train_receipt_fixture(root):
    root=Path(root)
    parent_rows={
        'train':[{'id':'synthetic-parent-train','messages':[{'role':'user','content':'Synthetic parent prompt.'},{'role':'assistant','content':'Synthetic parent answer.'}]}],
        'validation':[{'id':'synthetic-parent-validation','messages':[{'role':'user','content':'Synthetic parent prompt.'},{'role':'assistant','content':'Synthetic parent answer.'}]}],
    }
    parent_bytes={s:(json.dumps(rows[0],separators=(',',':'))+'\n').encode() for s,rows in parent_rows.items()}
    additions={}
    review_rows=[]
    for split,suffix in (('train','a'),('validation','b')):
        record_id=f'supplement-{suffix}'
        messages=[
            {'role':'system','content':'Synthetic lineage verifier fixture.'},
            {'role':'user','content':f'Synthetic prompt {suffix}.'},
            {'role':'assistant','content':f'Synthetic answer {suffix}.'},
        ]
        contract={'assistant_turn':1,'response_mode':'answer','language':'en','response_language':'en','required_facts':[],'forbidden_facts':[],'future_facts':[],'criteria':['fixture']}
        record={'id':record_id,'split':split,'review_status':'human_reviewed','messages':messages,'quality_contracts':[contract]}
        additions[split]=record
        review_rows.append({
            'review_key':f'{split}:{record_id}:1','split':split,'record_id':record_id,'assistant_turn':'1',
            'prefix_json':json.dumps(messages[:2],ensure_ascii=False,separators=(',',':')),
            'reference_answer':messages[2]['content'],
            'quality_contract_json':json.dumps(contract,ensure_ascii=False,separators=(',',':')),
            'decision':'approve','revised_answer':'','revised_quality_contract_json':'',
            'reviewer':'reviewer-fixture','reviewed_at':'2026-10-01T10:00:00+00:00','reason':'',
        })
    release_bytes={}
    for split in ('train','validation'):
        release_bytes[split]=parent_bytes[split]+(json.dumps(additions[split],ensure_ascii=False,separators=(',',':'))+'\n').encode()
        (root/f'{split}.jsonl').write_bytes(release_bytes[split])
        (root/f'lineage_parent_{split}.jsonl').write_bytes(parent_bytes[split])
    parent_files={f'{s}.jsonl':digest(root/f'lineage_parent_{s}.jsonl') for s in ('train','validation')}
    parent_manifest={'schema_version':4,'status':'human_attested_locked_before_training','locked':True,'files':parent_files}
    (root/'lineage_parent_manifest.json').write_text(json.dumps(parent_manifest),encoding='utf-8')
    parent_receipt={'schema_version':1,'review_type':'train_validation','test_only':False,'result_files':parent_files,'row_count':2,'reviewers':['reviewer-fixture'],'reviewed_at':['2026-10-01T10:00:00+00:00']}
    (root/'lineage_parent_train_validation_review_receipt.json').write_text(json.dumps(parent_receipt),encoding='utf-8')
    with (root/'supplement_review.csv').open('w',encoding='utf-8-sig',newline='') as handle:
        writer=csv.DictWriter(handle,fieldnames=FIELDS);writer.writeheader();writer.writerows(review_rows)
    review_sha=digest(root/'supplement_review.csv')
    release_hashes={f'{s}.jsonl':digest(root/f'{s}.jsonl') for s in ('train','validation')}
    supplement={'schema_version':1,'receipt_type':'train_validation_supplement_review','scope':'supplemental completion rows only; does not attest the full release','not_a_full_release_receipt':True,'covered_completion_rows':2,'added_records':{'train':1,'validation':1},'release_counts':{'train_records':2,'train_assistant_completions':2,'validation_records':2,'validation_assistant_completions':2},'covered_review_keys':[r['review_key'] for r in review_rows],'decisions':{'approve':2,'revise':0},'reviewers':['reviewer-fixture'],'reviewed_at':['2026-10-01T10:00:00+00:00'],'review_csv_sha256':review_sha,'parent_manifest_sha256':digest(root/'lineage_parent_manifest.json'),'parent_train_validation_receipt_sha256':digest(root/'lineage_parent_train_validation_review_receipt.json'),'parent_file_sha256':parent_files,'release_v3_sha256':release_hashes}
    (root/'supplement_review_receipt.json').write_text(json.dumps(supplement),encoding='utf-8')
    lineage_paths={
        'parent_manifest':'lineage_parent_manifest.json',
        'parent_receipt':'lineage_parent_train_validation_review_receipt.json',
        'parent_train':'lineage_parent_train.jsonl',
        'parent_validation':'lineage_parent_validation.jsonl',
        'supplement_receipt':'supplement_review_receipt.json',
        'supplement_review_csv':'supplement_review.csv',
    }
    lineage={f'{key}_path':name for key,name in lineage_paths.items()}
    lineage.update({f'{key}_sha256':digest(root/name) for key,name in lineage_paths.items()})
    lineage['completion_counts']={'parent':2,'supplement':2,'total':4}
    aggregate={'schema_version':2,'receipt_kind':'lineage_aggregate','review_type':'train_validation','test_only':False,'result_files':release_hashes,'row_count':4,'reviewers':['reviewer-fixture'],'reviewed_at':['2026-10-01T10:00:00+00:00'],'lineage':lineage}
    aggregate_path=root/'train_validation_review_receipt.json'
    aggregate_path.write_text(json.dumps(aggregate),encoding='utf-8')
    return aggregate_path,aggregate,release_hashes


def test_full_training_gate_requires_persisted_review_receipts(tmp_path):
    manifest=_locked_gate_fixture(tmp_path)
    assert verify_full_training_gate(tmp_path,manifest) is True


def test_full_training_gate_accepts_lineage_aware_train_validation_receipt(tmp_path):
    root=tmp_path/'lineaged-release';root.mkdir()
    train_receipt_path,train_receipt,train_files=_lineaged_train_receipt_fixture(root)
    test_path=root/'test.jsonl';test_path.write_text('{"synthetic_test_fixture":true}\n',encoding='utf-8')
    test_hash=digest(test_path)
    test_receipt={'schema_version':1,'review_type':'independent_test','test_only':False,'human_author':'author-fixture','result_files':{'test.jsonl':test_hash},'row_count':1,'reviewers':['reviewer-fixture'],'reviewed_at':['2026-10-01T10:00:00+00:00']}
    test_receipt_path=root/'independent_test_review_receipt.json';test_receipt_path.write_text(json.dumps(test_receipt),encoding='utf-8')
    files={**train_files,'test.jsonl':test_hash,'train_validation_review_receipt.json':digest(train_receipt_path),'independent_test_review_receipt.json':digest(test_receipt_path)}
    manifest={'schema_version':4,'status':'human_attested_locked_before_training','locked':True,'row_counts':{'train':2,'validation':2,'test':1},'files':files}
    attestation={'human_author':'author-fixture','reviewer':'reviewer-fixture','training_reviewed':True,'locked_before_training':True,'test_sha256':test_hash,'train_review_receipt_sha256':files['train_validation_review_receipt.json'],'test_review_receipt_sha256':files['independent_test_review_receipt.json']}
    (root/'human_test_attestation.json').write_text(json.dumps(attestation),encoding='utf-8')
    assert verify_full_training_gate(root,manifest) is True
    script=ROOT/'python/scripts/lock_llm_data.py'
    spec=importlib.util.spec_from_file_location('lock_llm_data_lineage_receipt_test',script)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    loaded,_=module._receipt(train_receipt_path,'train_validation',train_files,4,root=root)
    assert loaded['receipt_kind']=='lineage_aggregate'


def test_lineage_receipt_rejects_supplement_review_csv_tampering(tmp_path):
    root=tmp_path/'lineaged-release';root.mkdir()
    _,receipt,files=_lineaged_train_receipt_fixture(root)
    (root/'supplement_review.csv').write_bytes((root/'supplement_review.csv').read_bytes()+b'\n')
    with pytest.raises(ValueError,match='artifact hash mismatch'):
        from dusnx_core.llm_data import verify_train_validation_lineage_receipt
        verify_train_validation_lineage_receipt(root,receipt,files,4)


def test_lineage_receipt_rejects_review_key_mismatch_after_rehash(tmp_path):
    root=tmp_path/'lineaged-release';root.mkdir()
    receipt_path,receipt,files=_lineaged_train_receipt_fixture(root)
    supplement_path=root/'supplement_review_receipt.json'
    supplement=json.loads(supplement_path.read_text(encoding='utf-8'))
    supplement['covered_review_keys'][0]='train:wrong-record:1'
    supplement_path.write_text(json.dumps(supplement),encoding='utf-8')
    receipt['lineage']['supplement_receipt_sha256']=digest(supplement_path)
    receipt_path.write_text(json.dumps(receipt),encoding='utf-8')
    from dusnx_core.llm_data import verify_train_validation_lineage_receipt
    with pytest.raises(ValueError,match='review keys'):
        verify_train_validation_lineage_receipt(root,receipt,files,4)


def test_lineage_receipt_rejects_malformed_supplement_record(tmp_path):
    root=tmp_path/'lineaged-release';root.mkdir()
    receipt_path,receipt,_=_lineaged_train_receipt_fixture(root)
    rows=[json.loads(line) for line in (root/'train.jsonl').read_text(encoding='utf-8').splitlines() if line.strip()]
    del rows[-1]['quality_contracts']
    (root/'train.jsonl').write_text(''.join(json.dumps(row,ensure_ascii=False,separators=(',',':'))+'\n' for row in rows),encoding='utf-8',newline='\n')
    release_hashes={'train.jsonl':digest(root/'train.jsonl'),'validation.jsonl':digest(root/'validation.jsonl')}
    supplement_path=root/'supplement_review_receipt.json'
    supplement=json.loads(supplement_path.read_text(encoding='utf-8'))
    supplement['release_v3_sha256']=release_hashes
    supplement_path.write_text(json.dumps(supplement),encoding='utf-8')
    receipt['result_files']=release_hashes
    receipt['lineage']['supplement_receipt_sha256']=digest(supplement_path)
    receipt_path.write_text(json.dumps(receipt),encoding='utf-8')
    from dusnx_core.llm_data import verify_train_validation_lineage_receipt
    with pytest.raises(ValueError,match='Invalid supplement record structure'):
        verify_train_validation_lineage_receipt(root,receipt,release_hashes,4)


def test_full_training_gate_rejects_lineage_receipt_for_independent_test(tmp_path):
    manifest=_locked_gate_fixture(tmp_path)
    path=tmp_path/'independent_test_review_receipt.json';receipt=json.loads(path.read_text(encoding='utf-8'))
    receipt['schema_version']=2;path.write_text(json.dumps(receipt),encoding='utf-8')
    manifest['files'][path.name]=digest(path)
    attestation_path=tmp_path/'human_test_attestation.json';attestation=json.loads(attestation_path.read_text(encoding='utf-8'))
    attestation['test_review_receipt_sha256']=digest(path);attestation_path.write_text(json.dumps(attestation),encoding='utf-8')
    with pytest.raises(ValueError,match='receipt'):
        verify_full_training_gate(tmp_path,manifest)


@pytest.mark.parametrize('fault',['missing_receipt','tampered_receipt','wrong_result_hash'])
def test_full_training_gate_rejects_missing_or_wrong_review_receipts(tmp_path,fault):
    manifest=_locked_gate_fixture(tmp_path)
    receipt_path=tmp_path/'independent_test_review_receipt.json'
    if fault=='missing_receipt':
        receipt_path.unlink()
    elif fault=='tampered_receipt':
        receipt_path.write_text('{}',encoding='utf-8')
    else:
        receipt=json.loads(receipt_path.read_text(encoding='utf-8'));receipt['result_files']['test.jsonl']='0'*64
        receipt_path.write_text(json.dumps(receipt),encoding='utf-8')
        manifest['files'][receipt_path.name]=digest(receipt_path)
        attestation=json.loads((tmp_path/'human_test_attestation.json').read_text(encoding='utf-8'))
        attestation['test_review_receipt_sha256']=digest(receipt_path)
        (tmp_path/'human_test_attestation.json').write_text(json.dumps(attestation),encoding='utf-8')
    with pytest.raises(ValueError,match='receipt'):
        verify_full_training_gate(tmp_path,manifest)


@pytest.mark.parametrize('split',['train','test'])
def test_full_training_gate_rejects_receipt_row_count_mismatch_even_when_rehashed(tmp_path,split):
    manifest=_locked_gate_fixture(tmp_path)
    filename='train_validation_review_receipt.json' if split=='train' else 'independent_test_review_receipt.json'
    path=tmp_path/filename;receipt=json.loads(path.read_text(encoding='utf-8'))
    receipt['row_count']+=1;path.write_text(json.dumps(receipt),encoding='utf-8')
    manifest['files'][filename]=digest(path)
    attestation_path=tmp_path/'human_test_attestation.json';attestation=json.loads(attestation_path.read_text(encoding='utf-8'))
    attestation['train_review_receipt_sha256' if split=='train' else 'test_review_receipt_sha256']=digest(path)
    attestation_path.write_text(json.dumps(attestation),encoding='utf-8')
    with pytest.raises(ValueError,match='receipt'):
        verify_full_training_gate(tmp_path,manifest)


@pytest.mark.parametrize('bad_count',[True,-1,None])
def test_full_training_gate_rejects_invalid_row_count_types(tmp_path,bad_count):
    manifest=_locked_gate_fixture(tmp_path)
    path=tmp_path/'independent_test_review_receipt.json';receipt=json.loads(path.read_text(encoding='utf-8'))
    if bad_count is None:del receipt['row_count']
    else:receipt['row_count']=bad_count
    path.write_text(json.dumps(receipt),encoding='utf-8')
    manifest['files'][path.name]=digest(path)
    attestation_path=tmp_path/'human_test_attestation.json';attestation=json.loads(attestation_path.read_text(encoding='utf-8'))
    attestation['test_review_receipt_sha256']=digest(path);attestation_path.write_text(json.dumps(attestation),encoding='utf-8')
    with pytest.raises(ValueError,match='receipt'):
        verify_full_training_gate(tmp_path,manifest)


def test_full_training_gate_requires_attested_reviewer_in_both_receipts(tmp_path):
    manifest=_locked_gate_fixture(tmp_path)
    attestation_path=tmp_path/'human_test_attestation.json';attestation=json.loads(attestation_path.read_text(encoding='utf-8'))
    attestation['reviewer']='reviewer-c';attestation_path.write_text(json.dumps(attestation),encoding='utf-8')
    with pytest.raises(ValueError,match='reviewer'):
        verify_full_training_gate(tmp_path,manifest)


@pytest.mark.parametrize('fault',['missing','bool','negative'])
def test_full_training_gate_rejects_invalid_manifest_row_counts(tmp_path,fault):
    manifest=_locked_gate_fixture(tmp_path)
    if fault=='missing':manifest.pop('row_counts')
    elif fault=='bool':manifest['row_counts']['train']=True
    else:manifest['row_counts']['test']=-1
    with pytest.raises(ValueError,match='manifest schema'):
        verify_full_training_gate(tmp_path,manifest)


def test_full_training_gate_rejects_boolean_schema_version(tmp_path):
    manifest=_locked_gate_fixture(tmp_path);manifest['schema_version']=True
    with pytest.raises(ValueError,match='human-attested'):
        verify_full_training_gate(tmp_path,manifest)
    manifest=_locked_gate_fixture(tmp_path)
    path=tmp_path/'independent_test_review_receipt.json';receipt=json.loads(path.read_text(encoding='utf-8'))
    receipt['schema_version']=True;path.write_text(json.dumps(receipt),encoding='utf-8')
    manifest['files'][path.name]=digest(path)
    attestation_path=tmp_path/'human_test_attestation.json';attestation=json.loads(attestation_path.read_text(encoding='utf-8'))
    attestation['test_review_receipt_sha256']=digest(path);attestation_path.write_text(json.dumps(attestation),encoding='utf-8')
    with pytest.raises(ValueError,match='receipt'):
        verify_full_training_gate(tmp_path,manifest)


def test_lock_command_rejects_same_author_and_reviewer(monkeypatch):
    script=ROOT/'python/scripts/lock_llm_data.py'
    spec=importlib.util.spec_from_file_location('lock_llm_data_for_test',script)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    monkeypatch.setattr(sys,'argv',['lock_llm_data.py','--human-author','person-a','--reviewer','person-a','--train-review-receipt','missing-train.json','--test-review-receipt','missing-test.json','--attest-authored-reviewed-before-predictions'])
    with pytest.raises(ValueError,match='different people'):module.main()


def test_lock_command_persists_and_manifests_receipts(tmp_path,monkeypatch):
    data=_copy_sft(tmp_path);rows={s:read_sft(data/f'{s}.jsonl',s) for s in ('train','validation','test')}
    train_files={f'{s}.jsonl':digest(data/f'{s}.jsonl') for s in ('train','validation')}
    test_files={'test.jsonl':digest(data/'test.jsonl')}
    receipts=[]
    for filename,receipt in (
        ('train-receipt.json',{'schema_version':1,'review_type':'train_validation','test_only':False,'result_files':train_files,'row_count':sum(len(completion_rows(rows[s])) for s in ('train','validation')),'reviewers':['reviewer-b'],'reviewed_at':['2026-10-01T10:00:00+00:00']}),
        ('test-receipt.json',{'schema_version':1,'review_type':'independent_test','test_only':False,'human_author':'author-a','result_files':test_files,'row_count':len(completion_rows(rows['test'])),'reviewers':['reviewer-b'],'reviewed_at':['2026-10-01T10:00:00+00:00']}),
    ):
        path=tmp_path/filename;raw=json.dumps(receipt,indent=2).encode('utf-8');path.write_bytes(raw);receipts.append((path,raw))
    script=ROOT/'python/scripts/lock_llm_data.py'
    spec=importlib.util.spec_from_file_location('lock_llm_data_for_test',script)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    monkeypatch.setattr(sys,'argv',['lock_llm_data.py','--data',str(data),'--human-author','author-a','--reviewer','reviewer-b','--train-review-receipt',str(receipts[0][0]),'--test-review-receipt',str(receipts[1][0]),'--attest-authored-reviewed-before-predictions'])
    original_persist=module._persist_receipt
    changed_train_receipt=json.loads(receipts[0][1]);changed_train_receipt['reviewed_at']=['2026-10-02T10:00:00+00:00']
    changed_train_raw=json.dumps(changed_train_receipt,indent=2).encode('utf-8')
    changed_source=False
    def mutate_source_after_validation(raw,root,name):
        nonlocal changed_source
        if name=='train_validation_review_receipt.json' and not changed_source:
            receipts[0][0].write_bytes(changed_train_raw)
            changed_source=True
        return original_persist(raw,root,name)
    monkeypatch.setattr(module,'_persist_receipt',mutate_source_after_validation)
    module.main()
    manifest=json.loads((data/'manifest.json').read_text(encoding='utf-8'))
    assert manifest['locked'] is True
    assert manifest['schema_version']==4
    assert manifest['row_counts']=={s:len(completion_rows(rows[s])) for s in ('train','validation','test')}
    for source,raw in receipts:
        target=data/('train_validation_review_receipt.json' if source.name.startswith('train-') else 'independent_test_review_receipt.json')
        assert target.read_bytes()==raw
        assert manifest['files'][target.name]==digest(target)
    assert verify_file_manifest(data,manifest)
    assert verify_full_training_gate(data,manifest)
    with pytest.raises(ValueError,match='Existing frozen receipt differs'):
        module.main()
    assert (data/'train_validation_review_receipt.json').read_bytes()==receipts[0][1]
    assert verify_full_training_gate(data,json.loads((data/'manifest.json').read_text(encoding='utf-8')))


def test_lock_command_requires_reviewer_in_train_validation_receipt(tmp_path,monkeypatch):
    data=_copy_sft(tmp_path);rows={s:read_sft(data/f'{s}.jsonl',s) for s in ('train','validation','test')}
    train_files={f'{s}.jsonl':digest(data/f'{s}.jsonl') for s in ('train','validation')}
    test_files={'test.jsonl':digest(data/'test.jsonl')}
    receipts=[]
    for filename,receipt in (
        ('train-receipt.json',{'schema_version':1,'review_type':'train_validation','test_only':False,'result_files':train_files,'row_count':sum(len(completion_rows(rows[s])) for s in ('train','validation')),'reviewers':['reviewer-c'],'reviewed_at':['2026-10-01T10:00:00+00:00']}),
        ('test-receipt.json',{'schema_version':1,'review_type':'independent_test','test_only':False,'human_author':'author-a','result_files':test_files,'row_count':len(completion_rows(rows['test'])),'reviewers':['reviewer-b'],'reviewed_at':['2026-10-01T10:00:00+00:00']}),
    ):
        path=tmp_path/filename;path.write_text(json.dumps(receipt),encoding='utf-8');receipts.append(path)
    script=ROOT/'python/scripts/lock_llm_data.py'
    spec=importlib.util.spec_from_file_location('lock_llm_data_reviewer_test',script)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    monkeypatch.setattr(sys,'argv',['lock_llm_data.py','--data',str(data),'--human-author','author-a','--reviewer','reviewer-b','--train-review-receipt',str(receipts[0]),'--test-review-receipt',str(receipts[1]),'--attest-authored-reviewed-before-predictions'])
    with pytest.raises(ValueError,match='train/validation'):
        module.main()
    assert not (data/'train_validation_review_receipt.json').exists()


def test_lock_command_partial_receipt_write_does_not_lock_data(tmp_path,monkeypatch):
    data=_copy_sft(tmp_path);rows={s:read_sft(data/f'{s}.jsonl',s) for s in ('train','validation','test')}
    train_files={f'{s}.jsonl':digest(data/f'{s}.jsonl') for s in ('train','validation')}
    test_files={'test.jsonl':digest(data/'test.jsonl')}
    receipts=[]
    for filename,receipt in (
        ('train-receipt.json',{'schema_version':1,'review_type':'train_validation','test_only':False,'result_files':train_files,'row_count':sum(len(completion_rows(rows[s])) for s in ('train','validation')),'reviewers':['reviewer-b'],'reviewed_at':['2026-10-01T10:00:00+00:00']}),
        ('test-receipt.json',{'schema_version':1,'review_type':'independent_test','test_only':False,'human_author':'author-a','result_files':test_files,'row_count':len(completion_rows(rows['test'])),'reviewers':['reviewer-b'],'reviewed_at':['2026-10-01T10:00:00+00:00']}),
    ):
        path=tmp_path/filename;path.write_text(json.dumps(receipt),encoding='utf-8');receipts.append(path)
    script=ROOT/'python/scripts/lock_llm_data.py'
    spec=importlib.util.spec_from_file_location('lock_llm_data_partial_write_test',script)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    monkeypatch.setattr(sys,'argv',['lock_llm_data.py','--data',str(data),'--human-author','author-a','--reviewer','reviewer-b','--train-review-receipt',str(receipts[0]),'--test-review-receipt',str(receipts[1]),'--attest-authored-reviewed-before-predictions'])
    original_persist=module._persist_receipt;calls=0
    def fail_on_test_receipt(raw,root,name):
        nonlocal calls
        calls+=1
        if calls==2:raise OSError('simulated write failure')
        return original_persist(raw,root,name)
    monkeypatch.setattr(module,'_persist_receipt',fail_on_test_receipt)
    with pytest.raises(OSError,match='simulated write failure'):
        module.main()
    manifest=json.loads((data/'manifest.json').read_text(encoding='utf-8'))
    with pytest.raises(ValueError,match='human-attested'):
        verify_full_training_gate(data,manifest)


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
    assert set(receipt)=={'schema_version','review_type','test_only','human_author','human_authored_at','reviewers','reviewed_at','row_count','result_files'}
    assert receipt['schema_version']==1 and receipt['review_type']=='train_validation'
    assert receipt['test_only'] is True and receipt['row_count']==61
    assert receipt['human_author'] is None
    assert receipt['reviewers']==['test-only-reviewer']
    assert receipt['reviewed_at']==['2026-09-30T10:00:00+07:00']
    assert receipt['result_files']=={s+'.jsonl':digest(data/(s+'.jsonl')) for s in ('train','validation')}
    assert all(row['review_status']=='human_reviewed' for split in ('train','validation') for row in read_sft(data/f'{split}.jsonl',split))
    assert json.loads((data/'manifest.json').read_text())['status']=='human_review_complete_pending_lock'


def test_review_package_round_trip_receipt_uses_default_non_test_mode(tmp_path):
    data=_copy_sft(tmp_path);package=tmp_path/'package-normal-review-fixture'
    assert export_package(data,package,('train','validation'))==61
    _complete_review_csv(package/'review.csv',reviewer='fixture-reviewer-1',timestamp='2026-10-01T10:00:00+00:00')
    receipt=apply_package(data,package)
    assert receipt['test_only'] is False
    assert receipt['schema_version']==1 and receipt['review_type']=='train_validation'
    assert receipt['row_count']==61
    assert receipt['reviewers']==['fixture-reviewer-1']
    assert receipt['reviewed_at']==['2026-10-01T10:00:00+00:00']
    assert receipt['result_files']=={s+'.jsonl':digest(data/(s+'.jsonl')) for s in ('train','validation')}


def test_review_package_accepts_reserialized_json_columns(tmp_path):
    data=_copy_sft(tmp_path);package=tmp_path/'package'
    assert export_package(data,package,('train','validation'))==61
    rows=_complete_review_csv(package/'review.csv',reviewer='fixture-reviewer-1',timestamp='2026-10-01T10:00:00+00:00')
    for row in rows:
        for field in ('prefix_json','quality_contract_json'):
            row[field]=json.dumps(json.loads(row[field]),ensure_ascii=False,indent=1)
    with (package/'review.csv').open('w',encoding='utf-8-sig',newline='') as handle:
        writer=csv.DictWriter(handle,fieldnames=FIELDS);writer.writeheader();writer.writerows(rows)
    receipt=apply_package(data,package)
    assert receipt['row_count']==61


def test_review_package_rejects_changed_json_meaning(tmp_path):
    data=_copy_sft(tmp_path);package=tmp_path/'package'
    export_package(data,package,('train','validation'))
    rows=_complete_review_csv(package/'review.csv',reviewer='fixture-reviewer-1',timestamp='2026-10-01T10:00:00+00:00')
    contract=json.loads(rows[0]['quality_contract_json'])
    contract['forbidden_facts']=list(contract['forbidden_facts'])+['__tamper__']
    rows[0]['quality_contract_json']=json.dumps(contract,ensure_ascii=False)
    with (package/'review.csv').open('w',encoding='utf-8-sig',newline='') as handle:
        writer=csv.DictWriter(handle,fieldnames=FIELDS);writer.writeheader();writer.writerows(rows)
    with pytest.raises(ValueError,match='quality_contract_json'):
        apply_package(data,package)


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
    for row in rows:
        row['decision']='approve';row['reviewer']='test-only-independent-reviewer'
    with (package/'review.csv').open('w',encoding='utf-8-sig',newline='') as handle:
        writer=csv.DictWriter(handle,fieldnames=list(rows[0]))
        writer.writeheader();writer.writerows(rows)
    receipt=apply_package(data,package,allow_test_identities=True)
    assert receipt['schema_version']==1 and receipt['review_type']=='independent_test'
    assert receipt['test_only'] is True and receipt['human_author']=='human-author-a'
    assert receipt['human_authored_at']=='2026-09-30T10:00:00+07:00'
    assert receipt['reviewers']==['test-only-independent-reviewer']
    assert receipt['reviewed_at']==['2026-09-30T10:00:00+07:00']
    assert receipt['row_count']==len(rows)
    assert receipt['result_files']=={'test.jsonl':digest(test_path)}


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
    monkeypatch.setenv('DUSNX_LLM_EVAL_MODELS','qwen2.5:0.5b,dusnx-vi-candidate')
    def call(req,timeout):
        body=json.loads(req.data)
        assert body['model']=='dusnx-vi-candidate' and body['options']['temperature']==0
        return io.BytesIO(json.dumps({'done':True,'model':'dusnx-vi-candidate','message':{'content':'Xin chào'},'eval_count':4}).encode())
    monkeypatch.setattr('urllib.request.urlopen',call)
    r=evaluate(EvaluationRequest(model='dusnx-vi-candidate',messages=[{'role':'system','content':'Tiếng Việt'},{'role':'user','content':'Chào'}]))
    assert r['response_source']=='llm' and r['provider_called'] and r['provider_ok']
    assert r['model_used']=='dusnx-vi-candidate'


def test_eval_default_allowlist_is_base_only(monkeypatch):
    from apps.ai_api.llm_evaluation import EvaluationRequest,evaluate
    from fastapi import HTTPException
    monkeypatch.setenv('DUSNX_ENABLE_LLM_EVAL','1')
    monkeypatch.delenv('DUSNX_LLM_EVAL_MODELS',raising=False)
    req=EvaluationRequest(model='dusnx-vi-v2-20261105',messages=[{'role':'system','content':'Tiếng Việt'},{'role':'user','content':'Chào'}])
    with pytest.raises(HTTPException) as e:evaluate(req)
    assert e.value.status_code==400


def test_pair_eval_requires_explicit_candidate(tmp_path):
    spec=importlib.util.spec_from_file_location('pair_args',ROOT/'python/scripts/evaluate_llm_pair.py');mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
    with pytest.raises(SystemExit):mod.parse_args(['--output',str(tmp_path/'out')])
    args=mod.parse_args(['--output',str(tmp_path/'out'),'--candidate','dusnx-vi-v2-20261105'])
    assert args.candidate=='dusnx-vi-v2-20261105'
    assert mod.parse_args(['--output',str(tmp_path/'out'),'--ratings','ratings.csv']).candidate is None


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


def test_promotion_accepts_spreadsheet_float_ratings():
    spec=importlib.util.spec_from_file_location('pair_float',ROOT/'python/scripts/evaluate_llm_pair.py');mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
    rows=[dict(output_id=arm,case_id='x',arm=arm,provider_ok=True,provider_called=True,response_source='llm') for arm in ('base','candidate')]
    ratings=[dict(output_id=arm,reviewer='real-reviewer',reviewed_at='2026-11-07T01:22:23+07:00',**{c:'1.0' for c in mod.CRITERIA}) for arm in ('base','candidate')]
    assert mod.promotion(rows,ratings,True)['promote']
    ratings[0]['grounded']='0.0'
    assert mod.promotion(rows,ratings,True)['promote']
    for bad in ('0.5','','2','yes'):
        ratings[1]['grounded']=bad
        with pytest.raises(ValueError,match='0 or 1'):mod.promotion(rows,ratings,True)


def test_eval_api_requires_auth(monkeypatch):
    from apps.ai_api.main import app
    from fastapi.testclient import TestClient
    monkeypatch.setenv('DUSNX_ENABLE_LLM_EVAL','1')
    response=TestClient(app).post('/v1/llm-evaluation',json={'model':'qwen2.5:0.5b','messages':[{'role':'system','content':'test'},{'role':'user','content':'hello'}]})
    assert response.status_code==401


def _stage_module():
    spec=importlib.util.spec_from_file_location('stage_llm_release_test',ROOT/'python/scripts/stage_llm_release.py')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module


def _stage_test_row(index,status='needs_human_review'):
    project=f'Dự án Hồ Sen {index}'
    return {
        'id':f'test-human-{index:03d}','source':'human_designed','source_revision':'human-test-v1',
        'license':'CC0-1.0','generation_method':'human-authored','scenario_family':f'human_unique_family_{index:03d}',
        'sequence_id':f'human-seq-{index:03d}','user_id':f'fictional-human-{index:03d}','split':'test',
        'review_status':status,'data_kind':'designed_conversation',
        'messages':[
            {'role':'system','content':f'Bối cảnh giả lập: {project} đang dùng PostgreSQL.'},
            {'role':'user','content':f'{project} dùng database nào?'},
            {'role':'assistant','content':f'Theo bối cảnh hiện tại, {project} đang dùng PostgreSQL.'},
        ],
        'quality_contracts':[{
            'assistant_turn':1,'response_mode':'answer','language':'vi','response_language':'vi',
            'required_facts':['PostgreSQL'],'forbidden_facts':[],'future_facts':[],
        }],
    }


def _stage_release_fixture(tmp_path,test_count=6,test_status='needs_human_review',locked=False):
    release=tmp_path/'release';release.mkdir()
    _,_,release_hashes=_lineaged_train_receipt_fixture(release)
    release_manifest={
        'schema_version':1,'release':'llm-v2-supplement-v3',
        'status':'human_reviewed_supplement_pending_independent_test',
        'locked':locked,'training_allowed':False,'official_evaluation_allowed':False,
        'contains_test_split':False,'independent_test_created':False,
        'release_file_sha256':release_hashes,
    }
    (release/'release_manifest.json').write_text(json.dumps(release_manifest),encoding='utf-8')
    (release/'lineage_receipt_verification.json').write_text('{}\n',encoding='utf-8')
    test_path=tmp_path/'independent_test.jsonl'
    test_path.write_text(''.join(json.dumps(_stage_test_row(i,test_status),ensure_ascii=False,separators=(',',':'))+'\n' for i in range(test_count)),encoding='utf-8',newline='\n')
    return release,test_path


def test_stage_llm_release_builds_unlocked_pending_gate(tmp_path):
    release,test_path=_stage_release_fixture(tmp_path)
    out=tmp_path/'gate'
    summary=_stage_module().stage_release(release,out,test_path)
    assert summary['status']=='staged' and summary['test_sequences']==6
    assert summary['row_counts']=={'train':2,'validation':2,'test':6}
    manifest=json.loads((out/'manifest.json').read_text(encoding='utf-8'))
    assert manifest['status']=='human_authored_test_pending_review'
    assert manifest['locked'] is False and manifest['training_allowed'] is False
    assert set(manifest['files'])=={'train.jsonl','validation.jsonl','test.jsonl'}
    assert verify_file_manifest(out,manifest)
    assert (out/'test.jsonl').read_bytes()==test_path.read_bytes()
    assert (out/'train.jsonl').read_bytes()==(release/'train.jsonl').read_bytes()
    assert (out/'lineage_parent_manifest.json').is_file()
    assert not (out/'independent_test_review_receipt.json').exists()
    assert not (out/'human_test_attestation.json').exists()


def test_stage_llm_release_requires_a_fresh_output(tmp_path):
    release,test_path=_stage_release_fixture(tmp_path)
    out=tmp_path/'gate';out.mkdir()
    with pytest.raises(ValueError,match='must not exist'):
        _stage_module().stage_release(release,out,test_path)


def test_stage_llm_release_rejects_tampered_release(tmp_path):
    release,test_path=_stage_release_fixture(tmp_path)
    train=release/'train.jsonl';train.write_bytes(train.read_bytes()+b'\n')
    with pytest.raises(ValueError,match='hashes do not match'):
        _stage_module().stage_release(release,tmp_path/'gate',test_path)
    assert not (tmp_path/'gate').exists()


def test_stage_llm_release_rejects_locked_release(tmp_path):
    release,test_path=_stage_release_fixture(tmp_path,locked=True)
    with pytest.raises(ValueError,match='unlocked'):
        _stage_module().stage_release(release,tmp_path/'gate',test_path)


def test_stage_llm_release_requires_pending_human_test(tmp_path):
    release,test_path=_stage_release_fixture(tmp_path,test_status='human_reviewed')
    with pytest.raises(ValueError,match='needs_human_review'):
        _stage_module().stage_release(release,tmp_path/'gate',test_path)


def test_stage_llm_release_requires_6_to_12_sequences(tmp_path):
    release,test_path=_stage_release_fixture(tmp_path,test_count=5)
    with pytest.raises(ValueError,match='6-12'):
        _stage_module().stage_release(release,tmp_path/'gate',test_path)


def test_stage_llm_release_rejects_protected_output(tmp_path):
    release,test_path=_stage_release_fixture(tmp_path)
    with pytest.raises(ValueError,match='Protected'):
        _stage_module().stage_release(release,tmp_path/'reviewer'/'gate',test_path)
