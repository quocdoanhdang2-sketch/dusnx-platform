"""Human-operated pre-training freeze, never auto-claims human authorship."""
import argparse
import hashlib
from datetime import datetime,timezone
import json
from pathlib import Path
from dusnx_core.llm_data import audit,completion_rows,digest,read_sft,verify_file_manifest,verify_train_validation_lineage_receipt,write_json


def _receipt(path, expected_type, expected_files, expected_rows, root=None):
    receipt_path=Path(path);raw=receipt_path.read_bytes();receipt=json.loads(raw.decode('utf-8'))
    if not isinstance(receipt,dict):raise ValueError('Review receipt must be a JSON object')
    version=receipt.get('schema_version')
    allowed_version=type(version) is int and (version==1 or (expected_type=='train_validation' and version==2))
    if not allowed_version or receipt.get('review_type')!=expected_type or receipt.get('test_only') is not False:
        raise ValueError('A real human review receipt is required')
    if receipt.get('result_files')!=expected_files or type(receipt.get('row_count')) is not int or receipt.get('row_count')!=expected_rows:
        raise ValueError('Review receipt does not match the current reviewed data')
    reviewers=receipt.get('reviewers');reviewed_at=receipt.get('reviewed_at')
    if not isinstance(reviewers,list) or not reviewers or any(not isinstance(value,str) or not value.strip() for value in reviewers):
        raise ValueError('Review receipt is incomplete')
    if not isinstance(reviewed_at,list) or not reviewed_at or any(not isinstance(value,str) or not value.strip() for value in reviewed_at):
        raise ValueError('Review receipt is incomplete')
    if version==2:
        if root is None:raise ValueError('Lineage receipt verification requires the data root')
        verify_train_validation_lineage_receipt(root,receipt,expected_files,expected_rows)
    return receipt,raw


def _persist_receipt(raw, root, name):
    """Keep the exact reviewed receipt beside the frozen data without overwriting it."""
    target=root/name
    if target.is_symlink():
        raise ValueError(f'Frozen receipt must not be a symlink: {name}')
    if target.exists():
        if target.read_bytes()!=raw:
            raise ValueError(f'Existing frozen receipt differs: {name}')
    else:
        try:
            with target.open('xb') as handle:
                handle.write(raw)
                handle.flush()
        except FileExistsError:
            if target.read_bytes()!=raw:
                raise ValueError(f'Existing frozen receipt differs: {name}')
    return hashlib.sha256(raw).hexdigest()


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--data',default='datasets/llm_sft');p.add_argument('--human-author',required=True);p.add_argument('--reviewer',required=True);p.add_argument('--train-review-receipt',required=True);p.add_argument('--test-review-receipt',required=True);p.add_argument('--attest-authored-reviewed-before-predictions',action='store_true');a=p.parse_args()
    if not a.attest_authored_reviewed_before_predictions:raise ValueError('Explicit human attestation required; do not run as an agent on behalf of a person')
    if not a.human_author.strip() or not a.reviewer.strip():raise ValueError('Human author and reviewer are required')
    if a.human_author.strip()==a.reviewer.strip():raise ValueError('Human author and independent reviewer must be different people')
    root=Path(a.data);current=json.loads((root/'manifest.json').read_text(encoding='utf-8'));verify_file_manifest(root,current)
    rows={s:read_sft(root/f'{s}.jsonl',s) for s in ('train','validation','test')};audit(rows)
    if any(r['source']!='human_designed' or r['review_status']!='human_reviewed' for r in rows['test']):raise ValueError('Test must actually be human-authored and reviewed; AI draft is insufficient')
    if any(r['review_status']!='human_reviewed' for s in ('train','validation') for r in rows[s]):raise ValueError('Review train/validation before full SFT')
    train_files={f'{s}.jsonl':digest(root/f'{s}.jsonl') for s in ('train','validation')}
    test_files={'test.jsonl':digest(root/'test.jsonl')}
    row_counts={s:len(completion_rows(rows[s])) for s in ('train','validation','test')}
    train_receipt,train_receipt_raw=_receipt(a.train_review_receipt,'train_validation',train_files,row_counts['train']+row_counts['validation'],root=root)
    test_receipt,test_receipt_raw=_receipt(a.test_review_receipt,'independent_test',test_files,row_counts['test'],root=root)
    if a.reviewer.strip() not in train_receipt['reviewers']:
        raise ValueError('Reviewer does not match the train/validation review receipt')
    if test_receipt.get('human_author')!=a.human_author.strip() or a.reviewer.strip() not in test_receipt['reviewers']:
        raise ValueError('Author/reviewer do not match the independent test review receipt')
    train_receipt_hash=_persist_receipt(train_receipt_raw,root,'train_validation_review_receipt.json')
    test_receipt_hash=_persist_receipt(test_receipt_raw,root,'independent_test_review_receipt.json')
    now=datetime.now(timezone.utc).isoformat()
    write_json(root/'human_test_attestation.json',dict(human_author=a.human_author.strip(),reviewer=a.reviewer.strip(),locked_at=now,locked_before_training=True,training_reviewed=True,test_sha256=digest(root/'test.jsonl'),train_review_receipt_sha256=train_receipt_hash,test_review_receipt_sha256=test_receipt_hash,statement='A human authored the independent test and another human reviewed it without seeing predictions.'))
    files={f'{s}.jsonl':digest(root/f'{s}.jsonl') for s in rows}
    files['train_validation_review_receipt.json']=train_receipt_hash
    files['independent_test_review_receipt.json']=test_receipt_hash
    write_json(root/'manifest.json',dict(schema_version=4,status='human_attested_locked_before_training',locked=True,locked_at=now,source_revision='human-reviewed-release',row_counts=row_counts,files=files))


if __name__=='__main__':main()
