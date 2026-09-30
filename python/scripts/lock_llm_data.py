"""Human-operated pre-training freeze, never auto-claims human authorship."""
import argparse
from datetime import datetime,timezone
import json
from pathlib import Path
from dusnx_core.llm_data import audit,completion_rows,digest,read_sft,verify_file_manifest,write_json


def _receipt(path, expected_type, expected_files, expected_rows):
    receipt_path=Path(path);receipt=json.loads(receipt_path.read_text(encoding='utf-8'))
    if receipt.get('review_type')!=expected_type or receipt.get('test_only') is not False:
        raise ValueError('A real human review receipt is required')
    if receipt.get('result_files')!=expected_files or receipt.get('row_count')!=expected_rows:
        raise ValueError('Review receipt does not match the current reviewed data')
    if not receipt.get('reviewers') or not receipt.get('reviewed_at'):
        raise ValueError('Review receipt is incomplete')
    return receipt_path,receipt


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--data',default='datasets/llm_sft');p.add_argument('--human-author',required=True);p.add_argument('--reviewer',required=True);p.add_argument('--train-review-receipt',required=True);p.add_argument('--test-review-receipt',required=True);p.add_argument('--attest-authored-reviewed-before-predictions',action='store_true');a=p.parse_args()
    if not a.attest_authored_reviewed_before_predictions:raise ValueError('Explicit human attestation required; do not run as an agent on behalf of a person')
    if a.human_author.strip()==a.reviewer.strip():raise ValueError('Human author and independent reviewer must be different people')
    root=Path(a.data);current=json.loads((root/'manifest.json').read_text(encoding='utf-8'));verify_file_manifest(root,current)
    rows={s:read_sft(root/f'{s}.jsonl',s) for s in ('train','validation','test')};audit(rows)
    if any(r['source']!='human_designed' or r['review_status']!='human_reviewed' for r in rows['test']):raise ValueError('Test must actually be human-authored and reviewed; AI draft is insufficient')
    if any(r['review_status']!='human_reviewed' for s in ('train','validation') for r in rows[s]):raise ValueError('Review train/validation before full SFT')
    train_files={f'{s}.jsonl':digest(root/f'{s}.jsonl') for s in ('train','validation')}
    test_files={'test.jsonl':digest(root/'test.jsonl')}
    train_path,train_receipt=_receipt(a.train_review_receipt,'train_validation',train_files,sum(len(completion_rows(rows[s])) for s in ('train','validation')))
    test_path,test_receipt=_receipt(a.test_review_receipt,'independent_test',test_files,len(completion_rows(rows['test'])))
    if test_receipt.get('human_author')!=a.human_author.strip() or a.reviewer.strip() not in test_receipt['reviewers']:
        raise ValueError('Author/reviewer do not match the independent test review receipt')
    now=datetime.now(timezone.utc).isoformat()
    write_json(root/'human_test_attestation.json',dict(human_author=a.human_author.strip(),reviewer=a.reviewer.strip(),locked_at=now,locked_before_training=True,training_reviewed=True,test_sha256=digest(root/'test.jsonl'),train_review_receipt_sha256=digest(train_path),test_review_receipt_sha256=digest(test_path),statement='A human authored the independent test and another human reviewed it without seeing predictions.'))
    write_json(root/'manifest.json',dict(schema_version=2,status='human_attested_locked_before_training',locked_at=now,source_revision='human-reviewed-release',files={f'{s}.jsonl':digest(root/f'{s}.jsonl') for s in rows}))


if __name__=='__main__':main()
