"""Standalone SFT data contracts. No router benchmarks, DBs or logs are imported."""
from collections import Counter
import hashlib
import json
from pathlib import Path
import re
import unicodedata


def digest(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        for block in iter(lambda:f.read(1024*1024),b''):h.update(block)
    return h.hexdigest()


def write_json(path,value):
    p=Path(path);p.parent.mkdir(parents=True,exist_ok=True)
    p.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf-8',newline='\n')


def read_sft(path,split):
    # Fail before reading any protected location, including reviewer submissions.
    path=Path(path)
    forbidden=('holdout','reviewer','submission','benchmark','training-results')
    if any(x in str(path.resolve()).casefold() for x in forbidden):raise ValueError('Protected data location is not an SFT input')
    rows=[json.loads(line) for line in path.read_text(encoding='utf-8').splitlines() if line.strip()]
    validate(rows,split)
    return rows


def normalized(value):return ' '.join(unicodedata.normalize('NFC',value).casefold().split())


def validate(rows,split):
    ids=set()
    required=('id','source','source_revision','license','scenario_family','sequence_id','user_id','split','review_status','messages','data_kind')
    for r in rows:
        if any(not r.get(k) for k in required):raise ValueError('Missing SFT provenance/messages')
        if r['id'] in ids:raise ValueError('Duplicate record ID')
        ids.add(r['id'])
        if r['split']!=split:raise ValueError('Unexpected split')
        if r['source'] not in ('synthetic_designed','human_designed') or r['license']!='CC0-1.0':raise ValueError('Source not approved for this authored pilot')
        if not r['user_id'].startswith('fictional-'):raise ValueError('Only fictional identities accepted')
        if r['data_kind']!='designed_conversation':raise ValueError('Do not mislabel observed conversations')
        roles=[m['role'] for m in r['messages']]
        if roles[0]!='system' or roles[-1]!='assistant' or roles[1:]!=['user','assistant']*((len(roles)-1)//2):
            raise ValueError('Invalid system/user/assistant ordering')
        for m in r['messages']:
            text=m.get('content','')
            if not text.strip():raise ValueError('Empty message')
            if re.search(r'(?i)(bearer\s+\S+|[\w.+-]+@[\w.-]+\.[a-z]{2,}|\b\d{9,}\b|gh[pous]_[a-z0-9]{12,})',text):
                raise ValueError('Potential personal data or secret')
        if any(k.startswith(('gold_','expected_','prediction')) for k in r) and split!='test':raise ValueError('Evaluation labels in training')
    if not rows:raise ValueError('Empty partition')


def audit(partitions):
    seen={k:set() for k in ('id','sequence_id','user_id','scenario_family','prompt')}
    report={}
    for split,rows in partitions.items():
        validate(rows,split)
        prompts=[normalized(json.dumps(p['prompt'],ensure_ascii=False,sort_keys=True)) for p in completion_rows(rows)]
        values={k:{r[k] for r in rows} for k in ('id','sequence_id','user_id','scenario_family')}
        values['prompt']=set(prompts)
        for k,vs in values.items():
            if seen[k]&vs:raise ValueError(f'Cross-split leakage: {k}')
            seen[k]|=vs
        if len(set(prompts))!=len(prompts):raise ValueError('Duplicate prompt within split')
        lengths=[sum(len(m['content']) for m in r['messages']) for r in rows]
        report[split]=dict(sequences=len(values['sequence_id']),records=len(rows),
            assistant_pairs=sum(sum(m['role']=='assistant' for m in r['messages']) for r in rows),
            unique_prompts=len(set(prompts)),duplicate_prompt_rate=1-len(set(prompts))/len(prompts),
            scenario_distribution=dict(Counter(r['scenario_family'] for r in rows)),
            char_length=dict(min=min(lengths),max=max(lengths),mean=sum(lengths)/len(lengths)),
            sources=dict(Counter(r['source'] for r in rows)),review_status=dict(Counter(r['review_status'] for r in rows)))
    return report


def completion_rows(rows):
    """Each known assistant turn gets only its preceding context, never future turns."""
    return [dict(prompt=r['messages'][:i],completion=[m]) for r in rows
            for i,m in enumerate(r['messages']) if m['role']=='assistant']


def verify_file_manifest(root,manifest):
    root=Path(root).resolve()
    for name,expected in manifest['files'].items():
        if Path(name).is_absolute() or '\\' in name or ':' in name or '..' in Path(name).parts:raise ValueError('Unsafe artifact path')
        raw=root/name
        if any(p.is_symlink() for p in [raw,*raw.parents] if p!=root.parent):raise ValueError('Symlink artifact')
        path=(root/name).resolve()
        if not path.is_relative_to(root) or path.is_symlink():raise ValueError('Unsafe artifact path')
        if not path.is_file() or digest(path)!=expected:raise ValueError(f'Artifact checksum mismatch: {name}')
    return True
