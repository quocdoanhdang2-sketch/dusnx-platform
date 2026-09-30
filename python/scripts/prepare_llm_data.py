"""Audit only the dedicated SFT directory; never imports router datasets."""
import argparse
import json
from pathlib import Path
import random
from dusnx_core.llm_data import audit, digest, read_sft, verify_file_manifest, write_json


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--data',default='datasets/llm_sft')
    p.add_argument('--output',default='runtime/llm-audit')
    a=p.parse_args();root=Path(a.data);out=Path(a.output)
    lock=json.loads((root/'manifest.json').read_text(encoding='utf-8'))
    verify_file_manifest(root,lock)
    partitions={s:read_sft(root/f'{s}.jsonl',s) for s in ('train','validation','test')}
    report=audit(partitions)
    write_json(out/'audit.json',report)
    sample=random.Random(20260930).sample(partitions['train'],min(8,len(partitions['train'])))
    write_json(out/'human_review_sample.json',[dict(record=r,reviewer='',decision='',notes='') for r in sample])
    print(json.dumps(report,ensure_ascii=False,indent=2))


if __name__=='__main__':main()
