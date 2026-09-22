$ErrorActionPreference = "Stop"
Write-Host "[1/5] Creating virtual environment..."
py -3.12 -m venv .venv
Write-Host "[2/5] Activating..."
& .\.venv\Scripts\Activate.ps1
Write-Host "[3/5] Installing dependencies..."
python -m pip install --upgrade pip
pip install -e ".\python[dev]"
$env:PYTHONPATH="$PWD\python\src"
Write-Host "[4/5] Generating 10K synthetic events..."
python .\python\scripts\generate_synthetic.py --events 10000 --users 500 --out .\data\synthetic_10k.jsonl
Write-Host "[5/5] Running tests..."
pytest .\python\tests -q
Write-Host "Setup complete. You can demo bootstrap mode now with: docker compose up --build"
Write-Host "To train DUSN-X: python .\python\scripts\train.py --config .\configs\smoke.yaml"
