"""Separate completion-masked LoRA SFT. Offline smoke is random tiny Qwen, not trained base."""
import argparse
import importlib.metadata
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import yaml
from dusnx_core.llm_data import audit, completion_rows, digest, read_sft, verify_file_manifest, verify_full_training_gate, write_json
from dusnx_core.llm_artifacts import pack


def run(args):
    import torch
    from datasets import Dataset
    from peft import LoraConfig
    from transformers import AutoModelForCausalLM, AutoTokenizer, EarlyStoppingCallback, TrainerCallback, set_seed
    from trl import SFTConfig, SFTTrainer
    versions={k:importlib.metadata.version(k) for k in ('torch','transformers','trl','peft','accelerate','datasets','tokenizers','huggingface-hub')}
    required={'transformers':'4.56.2','trl':'0.23.1','peft':'0.17.1','accelerate':'1.10.1','datasets':'4.1.1','tokenizers':'0.22.0','huggingface-hub':'0.35.1'}
    if any(versions[k]!=v for k,v in required.items()) or versions['torch'].split('+')[0]!='2.8.0':raise ValueError('Install requirements/llm-sft.txt in a separate environment')
    cfg=yaml.safe_load(Path(args.config).read_text(encoding='utf-8'))
    if len(cfg['base_revision'])!=40:raise ValueError('Base revision must be immutable SHA')
    if not args.smoke and not torch.cuda.is_available():raise RuntimeError('Full SFT requires CUDA GPU; use --smoke on CPU')
    data=Path(args.data)
    lock=json.loads((data/'manifest.json').read_text(encoding='utf-8'))
    # Test is hashed for freeze integrity; its content/labels are NEVER loaded by training.
    verify_file_manifest(data,lock)
    if not args.smoke:
        verify_full_training_gate(data,lock)
    rows={s:read_sft(data/f'{s}.jsonl',s) for s in ('train','validation')}
    report=audit(rows)
    commit=subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip()
    contract=dict(config=cfg,data_hashes=lock['files'],smoke=args.smoke)
    out=Path(args.output);out.mkdir(parents=True,exist_ok=True)
    if args.resume:
        verify_file_manifest(out,json.loads((out/'artifact_manifest.json').read_text(encoding='utf-8')))
        prior=json.loads((out/'training_manifest.json').read_text(encoding='utf-8'))
        if prior['contract']!=contract:raise ValueError('Resume config/data/base contract changed')
        if prior['code_commit']!=commit or prior['versions']!=versions:raise ValueError('Resume requires original code commit and library versions')
        checkpoint=Path(args.resume).resolve()
        if not checkpoint.is_relative_to(out.resolve()) or not (checkpoint/'trainer_state.json').is_file():raise ValueError('Invalid resume checkpoint')
    elif any(out.iterdir()):raise ValueError('Output already exists; use --resume or new output')
    set_seed(cfg['seed'])
    bf16=not args.smoke and torch.cuda.is_bf16_supported()
    if args.smoke:
        from transformers import PreTrainedTokenizerFast, Qwen2Config, Qwen2ForCausalLM
        from tokenizers import Tokenizer
        from tokenizers.models import WordLevel
        from tokenizers.pre_tokenizers import Whitespace
        t=Tokenizer(WordLevel({'[PAD]':0,'[UNK]':1,'<|im_start|>':2,'<|im_end|>':3,'user':4,'assistant':5,'system':6},unk_token='[UNK]'))
        t.pre_tokenizer=Whitespace()
        tokenizer=PreTrainedTokenizerFast(tokenizer_object=t,pad_token='[PAD]',eos_token='<|im_end|>',unk_token='[UNK]')
        tokenizer.chat_template="{% for m in messages %}{{ '<|im_start|>' + m['role'] + '\\n' + m['content'] + '<|im_end|>\\n' }}{% endfor %}{% if add_generation_prompt %}{{ '<|im_start|>assistant\\n' }}{% endif %}"
        model=Qwen2ForCausalLM(Qwen2Config(vocab_size=len(tokenizer),hidden_size=32,intermediate_size=64,num_hidden_layers=1,num_attention_heads=2,num_key_value_heads=1,max_position_embeddings=1024,pad_token_id=0,eos_token_id=3))
        rows={s:r[:2] for s,r in rows.items()}
    else:
        tokenizer=AutoTokenizer.from_pretrained(cfg['base_model'],revision=cfg['base_revision'],trust_remote_code=False)
        kwargs=dict(revision=cfg['base_revision'],trust_remote_code=False,torch_dtype=torch.bfloat16 if bf16 else torch.float16)
        if cfg['qlora']:
            from transformers import BitsAndBytesConfig
            from peft import prepare_model_for_kbit_training
            if importlib.metadata.version('bitsandbytes')!='0.47.0':raise ValueError('Install requirements/llm-qlora.txt')
            kwargs['quantization_config']=BitsAndBytesConfig(load_in_4bit=True,bnb_4bit_quant_type='nf4',bnb_4bit_use_double_quant=True,bnb_4bit_compute_dtype=kwargs['torch_dtype'])
            kwargs['device_map']={'':torch.cuda.current_device()}
        model=AutoModelForCausalLM.from_pretrained(cfg['base_model'],**kwargs)
        if cfg['qlora']:model=prepare_model_for_kbit_training(model)
    tokenizer.pad_token=tokenizer.pad_token or tokenizer.eos_token
    model.config.use_cache=False
    pairs={s:completion_rows(r) for s,r in rows.items()}
    for values in pairs.values():
        for r in values:
            n=len(tokenizer.apply_chat_template(r['prompt']+r['completion'],tokenize=True))
            if n>cfg['max_length']:raise ValueError(f'Example length {n} exceeds max_length; revise config/data, never silently truncate answers')
    class StageBackup(TrainerCallback):
        def on_train_begin(self,args,state,control,**kwargs):
            if state.best_model_checkpoint:
                name=state.best_model_checkpoint.replace('\\','/').rsplit('/',1)[-1]
                target=out/name
                if not name.startswith('checkpoint-') or not target.is_dir():raise ValueError('Best checkpoint missing after restore')
                state.best_model_checkpoint=str(target)
        def on_save(self,args,state,control,**kwargs):
            write_json(out/'metrics.json',state.log_history)
            pack(out,out.parent/f'{out.name}-step-{state.global_step}.zip')
            if args_outer.stop_after_epoch and state.epoch>=args_outer.stop_after_epoch:control.should_training_stop=True
    args_outer=args
    manifest=dict(contract=contract,code_commit=commit,code_dirty=bool(subprocess.check_output(['git','status','--porcelain'],text=True).strip()),versions=versions,seed=cfg['seed'],status='running',kind='offline_random_tiny_smoke' if args.smoke else 'pretrained_instruct_lora_sft',gpu=torch.cuda.get_device_name(0) if torch.cuda.is_available() else None,audit=report,started_unix=time.time(),test_used_for_selection=False)
    write_json(out/'training_manifest.json',manifest)
    early_stop=EarlyStoppingCallback(early_stopping_patience=cfg['early_stopping_patience'])
    callbacks=[StageBackup(),early_stop]
    trainer=SFTTrainer(model=model,processing_class=tokenizer,
        args=SFTConfig(output_dir=str(out),num_train_epochs=2 if args.smoke else cfg['epochs'],per_device_train_batch_size=1 if args.smoke else cfg['batch_size'],per_device_eval_batch_size=1,gradient_accumulation_steps=1 if args.smoke else cfg['gradient_accumulation_steps'],learning_rate=cfg['learning_rate'],seed=cfg['seed'],data_seed=cfg['seed'],max_length=cfg['max_length'],completion_only_loss=True,assistant_only_loss=False,packing=False,bf16=bf16,fp16=not args.smoke and not bf16,use_cpu=args.smoke,gradient_checkpointing=not args.smoke,gradient_checkpointing_kwargs={'use_reentrant':False},eval_strategy='epoch',save_strategy='epoch',logging_strategy='steps',logging_steps=1,save_total_limit=2,load_best_model_at_end=True,metric_for_best_model='eval_loss',greater_is_better=False,report_to='none',dataloader_num_workers=0,save_safetensors=True),
        train_dataset=Dataset.from_list(pairs['train']),eval_dataset=Dataset.from_list(pairs['validation']),
        peft_config=LoraConfig(task_type='CAUSAL_LM',r=cfg['lora_r'],lora_alpha=cfg['lora_alpha'],lora_dropout=cfg['lora_dropout'],target_modules=cfg['target_modules']),callbacks=callbacks)
    example=trainer.train_dataset[0]
    mask=example.get('completion_mask')
    if mask is None or 0 not in mask or 1 not in mask:raise RuntimeError('Missing prompt/completion boundary')
    batch=trainer.data_collator([example])
    labels=batch['labels'][0].tolist()
    if any(labels[i]!=-100 for i,m in enumerate(mask) if m==0):raise RuntimeError('System/user tokens leaked into loss')
    if not any(labels[i]!=-100 for i,m in enumerate(mask) if m==1):raise RuntimeError('All assistant targets are masked')
    # Restore early-stopping patience as well as optimizer/RNG on staged resume.
    trainer.args.restore_callback_states_from_checkpoint=True
    result=trainer.train(resume_from_checkpoint=args.resume)
    trainer.save_model(str(out/'adapter'));tokenizer.save_pretrained(out/'adapter')
    trainer.save_state()
    write_json(out/'metrics.json',trainer.state.log_history)
    learned=any(p.detach().abs().sum().item()>0 for n,p in trainer.model.named_parameters() if 'lora_B' in n)
    if not learned:raise RuntimeError('No LoRA update observed')
    active_early_stop=next(c for c in trainer.callback_handler.callbacks if isinstance(c,EarlyStoppingCallback))
    ended_early=active_early_stop.early_stopping_patience_counter>=cfg['early_stopping_patience']
    manifest.update(status='smoke_complete' if args.smoke else ('stage_complete' if args.stop_after_epoch and trainer.state.epoch<cfg['epochs'] and not ended_early else 'training_complete'),metrics=result.metrics,best_checkpoint=trainer.state.best_model_checkpoint,epoch=trainer.state.epoch,completion_mask_verified=True,lora_update_verified=learned,early_stopped=ended_early)
    write_json(out/'training_manifest.json',manifest)
    pack(out,out.parent/f'{out.name}.zip')
    print(json.dumps(dict(status=manifest['status'],output=str(out),epoch=trainer.state.epoch)))


if __name__=='__main__':
    p=argparse.ArgumentParser()
    p.add_argument('--config',default='configs/llm_sft.yaml');p.add_argument('--data',default='datasets/llm_sft')
    p.add_argument('--output',required=True);p.add_argument('--smoke',action='store_true');p.add_argument('--resume');p.add_argument('--stop-after-epoch',type=int)
    run(p.parse_args())
