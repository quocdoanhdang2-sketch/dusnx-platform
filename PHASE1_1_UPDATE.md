# DUSN-X Phase 1.1 update

This update adds:

- high-precision routing constraints for explicit product commands;
- `routing_source` in API responses;
- mixed-intent synthetic examples;
- a 30,000-event smoke-v2 configuration;
- a hard-case evaluation script;
- pytest import-path correction;
- a one-command local startup script.

## Local training

```powershell
cd D:\Projects\dusnx-platform
.\python\.venv\Scripts\Activate.ps1
$env:PYTHONPATH="D:\Projects\dusnx-platform\python;D:\Projects\dusnx-platform\python\src"

python python\scripts\generate_synthetic.py --events 30000 --users 1000 --out data\synthetic_30k_v2.jsonl
python python\scripts\train.py --config configs\smoke_v2.yaml
python python\scripts\evaluate_hard_cases.py --checkpoint artifacts\dusnx_smoke_v2.pt --device cpu
```

## Run the v2 checkpoint

```powershell
$env:DUSNX_CHECKPOINT="D:\Projects\dusnx-platform\artifacts\dusnx_smoke_v2.pt"
$env:DUSNX_DEVICE="cpu"
cd D:\Projects\dusnx-platform\python
python -m uvicorn apps.ai_api.main:app --host 127.0.0.1 --port 8000
```

Synthetic results are pipeline evidence only. Report model-only and final hybrid-routing metrics separately.
