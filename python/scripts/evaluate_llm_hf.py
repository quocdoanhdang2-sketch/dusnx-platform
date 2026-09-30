"""One-shot HF base/adapter generation on frozen LLM test; never used in trainer."""
import argparse
import json
from pathlib import Path
import time
from dusnx_core.llm_data import digest, read_sft, verify_file_manifest, verify_full_training_gate, write_json


def main():
    import torch
    from transformers import AutoModelForCausalLM,AutoTokenizer,set_seed
    from peft import PeftModel
    p=argparse.ArgumentParser();p.add_argument('--run',required=True);p.add_argument('--data',default='datasets/llm_sft');p.add_argument('--output',required=True);a=p.parse_args()
    run=Path(a.run);out=Path(a.output);data=Path(a.data)
    if out.exists():raise ValueError('Use a new evaluation directory; do not tune repeatedly on test')
    manifest=json.loads((run/'training_manifest.json').read_text(encoding='utf-8'))
    if manifest['status']!='training_complete' or manifest['contract']['smoke']:raise ValueError('Completed pretrained SFT required')
    verify_file_manifest(run,json.loads((run/'artifact_manifest.json').read_text(encoding='utf-8')))
    verify_file_manifest(data,{'files':manifest['contract']['data_hashes']})
    data_manifest=json.loads((data/'manifest.json').read_text(encoding='utf-8'));verify_full_training_gate(data,data_manifest)
    cases=read_sft(data/'test.jsonl','test');cfg=manifest['contract']['config'];results=[]
    tok=AutoTokenizer.from_pretrained(run/'adapter',local_files_only=True)
    for arm in ('base','candidate'):
        model=AutoModelForCausalLM.from_pretrained(cfg['base_model'],revision=cfg['base_revision'],torch_dtype=torch.float32,trust_remote_code=False)
        if arm=='candidate':model=PeftModel.from_pretrained(model,run/'adapter')
        model=model.to('cuda' if torch.cuda.is_available() else 'cpu').eval()
        for c in cases:
            set_seed(cfg['seed'])
            ids=tok.apply_chat_template(c['messages'][:-1],add_generation_prompt=True,return_tensors='pt').to(model.device)
            start=time.perf_counter()
            with torch.no_grad():output=model.generate(ids,attention_mask=torch.ones_like(ids),do_sample=False,max_new_tokens=256,pad_token_id=tok.pad_token_id,eos_token_id=tok.eos_token_id)
            results.append(dict(case_id=c['id'],arm=arm,text=tok.decode(output[0,ids.shape[1]:],skip_special_tokens=True),elapsed_ms=(time.perf_counter()-start)*1000,response_source='llm',human_rating=None))
        del model
        if torch.cuda.is_available():torch.cuda.empty_cache()
    write_json(out/'sample_outputs.json',results)
    write_json(out/'manifest.json',dict(base_revision=cfg['base_revision'],test_sha256=digest(data/'test.jsonl'),review='pending human review; no automatic superiority claim'))


if __name__=='__main__':main()
