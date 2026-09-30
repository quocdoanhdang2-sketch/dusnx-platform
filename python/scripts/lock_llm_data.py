"""Human-operated pre-training freeze, never auto-claims human authorship."""
import argparse
from datetime import datetime,timezone
from pathlib import Path
from dusnx_core.llm_data import audit,digest,read_sft,write_json


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--data',default='datasets/llm_sft');p.add_argument('--human-author',required=True);p.add_argument('--reviewer',required=True);p.add_argument('--attest-authored-reviewed-before-predictions',action='store_true');a=p.parse_args()
    if not a.attest_authored_reviewed_before_predictions:raise ValueError('Explicit human attestation required; do not run as an agent on behalf of a person')
    root=Path(a.data);rows={s:read_sft(root/f'{s}.jsonl',s) for s in ('train','validation','test')};audit(rows)
    if any(r['source']!='human_designed' or r['review_status']!='human_reviewed' for r in rows['test']):raise ValueError('Test must actually be human-authored and reviewed; AI draft is insufficient')
    if any(r['review_status']!='human_reviewed' for s in ('train','validation') for r in rows[s]):raise ValueError('Review train/validation before full SFT')
    now=datetime.now(timezone.utc).isoformat()
    write_json(root/'manifest.json',dict(schema_version=1,status='human_attested_locked_before_training',locked_at=now,files={f'{s}.jsonl':digest(root/f'{s}.jsonl') for s in rows}))
    write_json(root/'human_test_attestation.json',dict(human_author=a.human_author,reviewer=a.reviewer,locked_at=now,locked_before_training=True,training_reviewed=True,test_sha256=digest(root/'test.jsonl')))


if __name__=='__main__':main()
