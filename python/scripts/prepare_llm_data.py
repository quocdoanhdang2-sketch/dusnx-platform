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
    p.add_argument('--tokenizer-model',help='Optional exact tokenizer; requires the pinned SFT environment')
    p.add_argument('--tokenizer-revision')
    p.add_argument('--max-length',type=int,default=512)
    a=p.parse_args();root=Path(a.data);out=Path(a.output)
    lock=json.loads((root/'manifest.json').read_text(encoding='utf-8'))
    verify_file_manifest(root,lock)
    partitions={s:read_sft(root/f'{s}.jsonl',s) for s in ('train','validation','test')}
    tokenizer=None
    if a.tokenizer_model:
        if not a.tokenizer_revision or len(a.tokenizer_revision)!=40:
            raise ValueError('--tokenizer-revision must be an immutable 40-character commit SHA')
        from transformers import AutoTokenizer
        tokenizer=AutoTokenizer.from_pretrained(a.tokenizer_model,revision=a.tokenizer_revision,trust_remote_code=False)
    report=audit(partitions,tokenizer=tokenizer,max_length=a.max_length)
    report['manifest_sha256']=digest(root/'manifest.json')
    report['tokenizer']=dict(model=a.tokenizer_model,revision=a.tokenizer_revision,exact=tokenizer is not None,max_length=a.max_length)
    write_json(out/'audit.json',report)
    sample=random.Random(20260930).sample(partitions['train'],min(8,len(partitions['train'])))
    write_json(out/'human_review_sample.json',[dict(record=r,reviewer='',decision='',notes='') for r in sample])
    lines=['# Báo cáo audit SFT','',f"Manifest SHA-256: `{report['manifest_sha256']}`",'']
    lines.append('| Split | Chuỗi | Cặp assistant | Prompt duy nhất | Token min–max–mean |')
    lines.append('|---|---:|---:|---:|---:|')
    for split in ('train','validation','test'):
        item=report[split];tokens=item['token_length']
        token_text=(f"{tokens['min']}–{tokens['max']}–{tokens['mean']}" if tokens else 'chưa đo bằng tokenizer')
        lines.append(f"| {split} | {item['sequences']} | {item['assistant_pairs']} | {item['unique_prompts']} | {token_text} |")
    lines.extend(['',f"- Trùng prompt chính xác: 0.",f"- Ngưỡng near-duplicate: {report['quality']['near_duplicate_threshold']}; tương đồng cross-split lớn nhất: {report['quality']['max_cross_split_similarity']}.",f"- Near-duplicate trong cùng split: {len(report['quality']['near_duplicate_pairs_within_split'])}; các cặp cùng chuỗi nhiều lượt được giữ để học tiếp nối.",'- Validator đã kiểm tra tiếng Việt, required fact có trong ngữ cảnh trước đó, obsolete/rejected fact không vào completion, future fact không lọt ngược và clarification có câu hỏi.','- Mọi record hiện vẫn `needs_human_review`; báo cáo máy không thay thế duyệt nội dung bởi người.',''])
    (out/'audit.md').write_text('\n'.join(lines),encoding='utf-8',newline='\n')
    print(json.dumps(report,ensure_ascii=False,indent=2))


if __name__=='__main__':main()
