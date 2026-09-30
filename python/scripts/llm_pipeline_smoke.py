"""Offline smoke verifies staged resume matches uninterrupted tiny LoRA training."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys


def main():
    p=argparse.ArgumentParser();p.add_argument('--output',required=True);a=p.parse_args()
    root=Path(a.output)
    if root.exists():raise ValueError('Use a new smoke output directory')
    root.mkdir(parents=True)
    os.environ['HF_HUB_OFFLINE']='1';os.environ['TRANSFORMERS_OFFLINE']='1'
    def call(*args):subprocess.run([sys.executable,'python/scripts/finetune_llm.py','--smoke',*map(str,args)],check=True)
    staged=root/'staged';whole=root/'whole'
    call('--output',staged,'--stop-after-epoch',1)
    last=sorted(staged.glob('checkpoint-*'),key=lambda p:int(p.name.split('-')[-1]))[-1]
    call('--output',staged,'--resume',last)
    call('--output',whole)
    import torch
    from safetensors.torch import load_file
    left=load_file(staged/'adapter/adapter_model.safetensors');right=load_file(whole/'adapter/adapter_model.safetensors')
    assert left.keys()==right.keys()
    for name in left:torch.testing.assert_close(left[name],right[name],rtol=1e-5,atol=1e-7,msg=f'Resume diverged: {name}')
    manifest=json.loads((staged/'training_manifest.json').read_text(encoding='utf-8'))
    assert manifest['epoch']==2 and manifest['completion_mask_verified'] and manifest['multi_turn_completion_mask_verified'] and manifest['lora_update_verified']
    result=subprocess.run([sys.executable,'python/scripts/export_llm.py','merge-gguf','--run',str(staged),'--output',str(root/'must-not-export')],capture_output=True,text=True)
    assert result.returncode!=0 and 'Only completed pretrained SFT' in result.stderr
    report={'status':'passed','kind':'random_tiny_qwen_cpu_not_pretrained_finetune','resume_matches_uninterrupted':True,'completion_mask_verified':True,'multi_turn_completion_mask_verified':True,'lora_update_verified':True,'smoke_export_rejected':True,'versions':manifest['versions']}
    (root/'smoke_report.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(report))


if __name__=='__main__':main()
