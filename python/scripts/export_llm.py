"""Merge exact-base LoRA and export GGUF with an immutable llama.cpp converter."""
import argparse
import json
from pathlib import Path
import shutil
import subprocess
import sys
from dusnx_core.llm_data import verify_file_manifest, write_json
from dusnx_core.llm_artifacts import pack, unpack

LLAMA_COMMIT='a7a98e0fffed794396b3fbad4dcdbbc184963645'  # upstream b6500


def export(run,output,converter):
    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer
    from peft import PeftModel
    from huggingface_hub import hf_hub_download
    run=Path(run);out=Path(output)
    manifest=json.loads((run/'training_manifest.json').read_text(encoding='utf-8'))
    if manifest['contract']['smoke'] or manifest['status']!='training_complete':raise ValueError('Only completed pretrained SFT can be exported')
    verify_file_manifest(run,json.loads((run/'artifact_manifest.json').read_text(encoding='utf-8')))
    if out.exists() and any(out.iterdir()):raise ValueError('Export destination must be empty')
    out.mkdir(parents=True,exist_ok=True);cfg=manifest['contract']['config'];merged=out/'merged'
    base=AutoModelForCausalLM.from_pretrained(cfg['base_model'],revision=cfg['base_revision'],torch_dtype=torch.float32,trust_remote_code=False)
    model=PeftModel.from_pretrained(base,run/'adapter').merge_and_unload()
    model.save_pretrained(merged,safe_serialization=True)
    tok=AutoTokenizer.from_pretrained(run/'adapter',local_files_only=True);tok.save_pretrained(merged)
    license_path=hf_hub_download(cfg['base_model'],'LICENSE',revision=cfg['base_revision'])
    shutil.copyfile(license_path,out/'LICENSE.base')
    (out/'NOTICE').write_text('Qwen2.5-0.5B-Instruct, Alibaba Cloud. Modified by DUSN-X LoRA SFT; see training_manifest.json for base revision and data.\n',encoding='utf-8')
    shutil.copyfile(run/'training_manifest.json',out/'training_manifest.json')
    converter=Path(converter)
    if not converter.exists():subprocess.run(['git','clone','--filter=blob:none','https://github.com/ggml-org/llama.cpp.git',str(converter)],check=True)
    if subprocess.check_output(['git','-C',str(converter),'status','--porcelain','--untracked-files=no'],text=True).strip():raise ValueError('Converter has tracked edits; use a clean separate directory')
    subprocess.run(['git','-C',str(converter),'checkout','--detach',LLAMA_COMMIT],check=True)
    actual=subprocess.check_output(['git','-C',str(converter),'rev-parse','HEAD'],text=True).strip()
    if actual!=LLAMA_COMMIT:raise ValueError('Converter revision mismatch')
    # Separate converter venv: its dependencies must not modify the SFT environment.
    env=converter/'converter-venv'
    subprocess.run([sys.executable,'-m','venv',str(env)],check=True)
    py=env/('Scripts/python.exe' if sys.platform=='win32' else 'bin/python')
    subprocess.run([str(py),'-m','pip','install','-r',str(converter/'requirements/requirements-convert_hf_to_gguf.txt')],check=True)
    gguf=out/'dusnx-vi-v1-f16.gguf'
    command=[str(py),str(converter/'convert_hf_to_gguf.py'),str(merged),'--outfile',str(gguf),'--outtype','f16']
    subprocess.run(command,check=True)
    if gguf.open('rb').read(4)!=b'GGUF':raise ValueError('Invalid GGUF output')
    versions=subprocess.check_output([str(py),'-m','pip','freeze','--all'],text=True).splitlines()
    write_json(out/'export_manifest.json',dict(llama_cpp_commit=actual,converter_dependencies=versions,format='GGUF',quantization='F16',command=command,base_model=cfg['base_model'],base_revision=cfg['base_revision'],promotion='not_evaluated'))
    pack(out,out.parent/f'{out.name}.zip')


if __name__=='__main__':
    p=argparse.ArgumentParser();s=p.add_subparsers(dest='command',required=True)
    e=s.add_parser('merge-gguf');e.add_argument('--run',required=True);e.add_argument('--output',required=True);e.add_argument('--converter',default='runtime/llama.cpp')
    z=s.add_parser('pack');z.add_argument('--root',required=True);z.add_argument('--zip',required=True)
    u=s.add_parser('unpack');u.add_argument('--zip',required=True);u.add_argument('--sha256',required=True);u.add_argument('--output',required=True)
    v=s.add_parser('verify');v.add_argument('--root',required=True)
    a=p.parse_args()
    if a.command=='merge-gguf':export(a.run,a.output,a.converter)
    elif a.command=='pack':pack(a.root,a.zip)
    elif a.command=='unpack':unpack(a.zip,a.output,a.sha256)
    else:
        root=Path(a.root);manifest=json.loads((root/'artifact_manifest.json').read_text(encoding='utf-8'))
        verify_file_manifest(root,manifest)
        actual={p.relative_to(root).as_posix() for p in root.rglob('*') if p.is_file() and p.name not in ('artifact_manifest.json','Modelfile.local')}
        if actual!=set(manifest['files']):raise ValueError('Artifact contains unlisted or missing files')
