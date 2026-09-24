$ErrorActionPreference = "Stop"
Write-Host "[1/5] Creating virtual environment..."
py -3.12 -m venv .venv
Write-Host "[2/5] Activating..."
& .\.venv\Scripts\Activate.ps1
Write-Host "[3/5] Installing dependencies..."
python -m pip install --upgrade pip
Push-Location .\python
pip install -e ".[dev]"
Pop-Location
$env:PYTHONPATH="$PWD\python\src"
Write-Host "[4/5] Generating 30K v2 synthetic events..."
python .\python\scripts\generate_synthetic.py --events 30000 --users 1000 --out .\data\synthetic_30k_v2.jsonl
Write-Host "[5/5] Running tests..."
pytest .\python\tests -q
Write-Host "Setup complete. You can demo bootstrap mode now with: docker compose up --build"
Write-Host "To train DUSN-X v2: python .\python\scripts\train.py --config .\configs\smoke_v2.yaml"
