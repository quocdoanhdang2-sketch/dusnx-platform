"""Pick an Ollama model that fits the machine running DUSN-X.

The same checkout runs on a 4 GB laptop GPU and on a 16 GB desktop. One
hard-coded model is either too large (Ollama spills layers to CPU or fails to
load) or needlessly weak. This module resolves one profile per process:

    DUSNX_OLLAMA_MODEL=<tag>   explicit choice; always wins
    DUSNX_MODEL_PROFILE=auto   auto (default) | low | mid | high
    DUSNX_MODEL_VRAM_GB=<n>    override detection (containers, CI, CPU, Apple)

Auto selection never downloads anything. It only considers models already
installed in Ollama, stays inside the Qwen2.5 instruct family, and reports a
missing preferred model in /health so the operator can decide to pull it.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import time
import urllib.request
from typing import Iterable, Optional

# Approximate resident VRAM per tag (weights + 4k KV cache + runtime overhead),
# measured on this project's machine: 1.5B used 1.2 GB and 3B used 2.2 GB.
_MODEL_VRAM_GB = {
    "0.5b": 0.7,
    "1.5b": 1.8,
    "3b": 3.0,
    "7b": 5.4,
    "14b": 10.0,
    "32b": 21.0,
}

# Ordered best-first within each tier. Only Qwen2.5 instruct bases are eligible:
# qwen3 always emits <think> on the supported Ollama build, and dusnx-vi-*
# candidates are evaluation artifacts that were never promoted to runtime.
_TIER_PREFERENCE = {
    "low": ("qwen2.5:1.5b-instruct", "qwen2.5:3b-instruct", "qwen2.5:0.5b"),
    "mid": ("qwen2.5:7b-instruct", "qwen2.5:3b-instruct", "qwen2.5:1.5b-instruct"),
    "high": ("qwen2.5:14b-instruct", "qwen2.5:7b-instruct", "qwen2.5:3b-instruct"),
}
_TIER_LIMITS = (("low", 6.0), ("mid", 12.0), ("high", float("inf")))
_TIER_CAP = {"low": 6.0, "mid": 12.0, "high": float("inf")}
_DEFAULT_MODEL = "qwen2.5:1.5b-instruct"
_SIZE_RE = re.compile(r"(\d+(?:\.\d+)?)b(?:[-:]|$)", re.IGNORECASE)

_VRAM_CACHE: dict = {"probed": False, "gb": None, "source": "unknown"}
_MODELS_CACHE: dict = {"key": None, "names": None, "expires": 0.0}


def _parse_gb(value: str) -> Optional[float]:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if number > 0 else None


def _detect_vram() -> dict:
    """Return {"gb": float|None, "source": str}; cached for the process."""
    override = _parse_gb(os.getenv("DUSNX_MODEL_VRAM_GB", ""))
    if override is not None:
        return {"gb": override, "source": "env"}
    if _VRAM_CACHE["probed"]:
        return {"gb": _VRAM_CACHE["gb"], "source": _VRAM_CACHE["source"]}

    gb: Optional[float] = None
    source = "unknown"
    exe = shutil.which("nvidia-smi")
    if exe:
        try:
            flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
            completed = subprocess.run(
                [exe, "--query-gpu=memory.total", "--format=csv,noheader,nounits"],
                capture_output=True, text=True, timeout=2.0, creationflags=flags, check=False)
            values = []
            for line in completed.stdout.splitlines():
                line = line.strip()
                if line.isdigit():
                    values.append(float(line))
            if values:
                gb = max(values) / 1024.0
                source = "nvidia-smi"
        except (OSError, subprocess.SubprocessError):
            pass
    if gb is None:
        try:
            import torch
            if torch.cuda.is_available():
                gb = torch.cuda.get_device_properties(0).total_memory / 1024 ** 3
                source = "torch"
        except Exception:
            pass

    _VRAM_CACHE.update(probed=True, gb=round(gb, 1) if gb else None, source=source)
    return {"gb": _VRAM_CACHE["gb"], "source": source}


def detect_vram_gb() -> Optional[float]:
    return _detect_vram()["gb"]


def _tier_for(vram_gb: Optional[float]) -> str:
    if vram_gb is None:
        return "low"
    for name, upper in _TIER_LIMITS:
        if vram_gb < upper:
            return name
    return "high"


def _approx_vram(tag: str) -> Optional[float]:
    tail = tag.split(":")[-1]
    match = _SIZE_RE.search(tail)
    return _MODEL_VRAM_GB.get(match.group(1).lower()) if match else None


def _fits(tag: str, vram_gb: Optional[float]) -> bool:
    if vram_gb is None:
        return True
    needed = _approx_vram(tag)
    return needed is not None and needed <= vram_gb


def _tag_matches(configured: str, available: str) -> bool:
    return configured == available or (":" not in configured and available == configured + ":latest")


def _is_installed(tag: str, names: Iterable[str]) -> bool:
    return any(_tag_matches(tag, name) for name in names)


def _auto_selectable(tag: str) -> bool:
    return tag.lower().startswith("qwen2.5:") and _approx_vram(tag) is not None


def _tier_budget(tier: str, vram_gb: Optional[float]) -> Optional[float]:
    """VRAM budget for a tier, so a forced low profile never loads a 14B model."""
    cap = _TIER_CAP[tier]
    if vram_gb is None:
        return None if cap == float("inf") else cap
    return min(vram_gb, cap)


def _installed_models() -> Optional[list[str]]:
    """Cached /api/tags lookup. None means Ollama could not be asked."""
    now = time.monotonic()
    url = os.getenv("DUSNX_OLLAMA_URL", "http://127.0.0.1:11434").rstrip("/")
    if _MODELS_CACHE["key"] == url and now < _MODELS_CACHE["expires"]:
        return _MODELS_CACHE["names"]
    names: Optional[list[str]] = None
    try:
        request = urllib.request.Request(f"{url}/api/tags", method="GET")
        with urllib.request.urlopen(request, timeout=1.0) as response:
            data = json.loads(response.read().decode())
        if isinstance(data, dict) and isinstance(data.get("models"), list):
            names = [m["name"] for m in data["models"]
                     if isinstance(m, dict) and isinstance(m.get("name"), str)]
    except Exception:
        names = None
    _MODELS_CACHE.update(key=url, names=names, expires=now + (60.0 if names is not None else 10.0))
    return names


def remember_installed(names: Iterable[str]) -> None:
    """Reuse a model list that a health check already fetched."""
    url = os.getenv("DUSNX_OLLAMA_URL", "http://127.0.0.1:11434").rstrip("/")
    _MODELS_CACHE.update(key=url, names=[name for name in names if isinstance(name, str)],
                         expires=time.monotonic() + 60.0)


def _select_model(tier: str, names: Optional[list[str]], vram_gb: Optional[float]) -> tuple[str, str, Optional[str]]:
    preference = _TIER_PREFERENCE[tier]
    fitting = [tag for tag in preference if _fits(tag, vram_gb)] or list(preference)
    preferred = preference[0]
    if names is None:
        return fitting[0], "preferred", None
    for tag in fitting:
        if _is_installed(tag, names):
            warning = "preferred_model_missing" if tag != preferred else None
            return tag, "installed", warning
    fallback = [name for name in names if _auto_selectable(name) and _fits(name, vram_gb)]
    fallback.sort(key=lambda name: _approx_vram(name) or 0.0, reverse=True)
    if fallback:
        return fallback[0], "installed_fallback", "preferred_model_missing"
    return fitting[0], "unavailable", "preferred_model_missing"


def resolve_model_profile(installed: Optional[Iterable[str]] = None,
                          vram_gb: Optional[float] = None) -> dict:
    """Resolve the runtime model for this machine.

    ``installed`` and ``vram_gb`` exist so tests (and health checks that already
    fetched /api/tags) can pass known values without extra probes.
    """
    mode = os.getenv("DUSNX_MODEL_PROFILE", "auto").strip().lower() or "auto"
    if mode not in ("auto", "low", "mid", "high"):
        mode = "auto"
    detection = _detect_vram() if vram_gb is None else {"gb": vram_gb, "source": "explicit"}
    detected_gb = detection["gb"]
    detected_tier = _tier_for(detected_gb)
    tier = mode if mode in ("low", "mid", "high") else detected_tier

    names: Optional[list[str]]
    if installed is None:
        names = _installed_models()
    else:
        names = [name for name in installed if isinstance(name, str)]

    profile = {
        "mode": mode,
        "tier": tier,
        "detected_tier": detected_tier,
        "vram_gb": detected_gb,
        "vram_source": detection["source"],
        "preferred_model": _TIER_PREFERENCE[tier][0],
        "installed_count": None if names is None else len(names),
    }

    explicit = os.getenv("DUSNX_OLLAMA_MODEL", "").strip()
    if explicit:
        profile.update(model=explicit, source="env", warning=None, pull_hint=None)
        return profile

    model, source, warning = _select_model(tier, names, _tier_budget(tier, detected_gb))
    profile.update(model=model, source=source, warning=warning)
    if warning:
        profile["pull_hint"] = f"ollama pull {_TIER_PREFERENCE[tier][0]}"
    else:
        profile["pull_hint"] = None
    return profile


def get_model() -> str:
    """Return the model tag the provider should call."""
    explicit = os.getenv("DUSNX_OLLAMA_MODEL", "").strip()
    if explicit:
        return explicit
    return resolve_model_profile()["model"] or _DEFAULT_MODEL
