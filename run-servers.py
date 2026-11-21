import os
import sys
import subprocess
import time
import urllib.request
from pathlib import Path

ROOT = Path(r"D:\Projects\dusnx-platform")
PYTHON_EXE = ROOT / "python/.venv/Scripts/python.exe"
if not PYTHON_EXE.exists():
    PYTHON_EXE = Path(sys.executable)

def ensure_ollama():
    try:
        with urllib.request.urlopen("http://127.0.0.1:11434/api/tags", timeout=2) as r:
            return
    except Exception:
        pass
    ollama_bin = Path(r"D:\Apps\Ollama\ollama.exe")
    if ollama_bin.exists():
        print("Starting Ollama background server...")
        subprocess.Popen([str(ollama_bin), "serve"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        time.sleep(2)

ensure_ollama()

CHECKPOINT = ROOT / "training-results/colab-run-01/extracted/dusnx-router-full-01/router.pt"
GW_DLL = ROOT / "runtime/gateway-8090/Dusnx.Gateway.dll"
if not GW_DLL.exists():
    GW_DLL = ROOT / "gateway-dotnet/bin/Release/net8.0/Dusnx.Gateway.dll"

ai_env = {
    **os.environ,
    "PYTHONPATH": f"{ROOT}/python;{ROOT}/python/src",
    "DUSNX_CHECKPOINT": str(CHECKPOINT),
    "DUSNX_DEVICE": "cpu",
    "DUSNX_DATA_DIR": str(ROOT / "python/data"),
    "DUSNX_PROVIDER": "ollama",
    "DUSNX_OLLAMA_MODEL": "qwen2.5:1.5b-instruct",
    "DUSNX_ENABLE_LLM_EVAL": "0",
}

print(f"Starting FastAPI on port 8010 with {PYTHON_EXE}...")
p_ai = subprocess.Popen(
    [str(PYTHON_EXE), "-m", "uvicorn", "apps.ai_api.main:app", "--host", "127.0.0.1", "--port", "8010"],
    cwd=str(ROOT),
    env=ai_env,
)

time.sleep(3)

gw_env = {
    **os.environ,
    "AI_API_URL": "http://127.0.0.1:8010",
    "DUSNX_DATA_DIR": str(ROOT / "runtime/gateway-data"),
    "DUSNX_WEB_UI_DIR": str(ROOT / "web-ui"),
}

print(f"Starting Gateway on port 8090 with {GW_DLL}...")
p_gw = subprocess.Popen(
    ["dotnet", str(GW_DLL), "--urls", "http://127.0.0.1:8090"],
    cwd=str(ROOT),
    env=gw_env,
)

print("Both servers launched successfully! Keeping alive...")
p_ai.wait()
p_gw.wait()
