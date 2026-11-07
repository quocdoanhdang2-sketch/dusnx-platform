"""Adaptive model profile: same code must fit a 4 GB laptop and a 16 GB desktop."""
import io
import json

import pytest

from apps.ai_api import model_profile, provider


@pytest.fixture(autouse=True)
def clean_model_env(monkeypatch):
    for name in ("DUSNX_OLLAMA_MODEL", "DUSNX_MODEL_PROFILE", "DUSNX_MODEL_VRAM_GB"):
        monkeypatch.delenv(name, raising=False)


@pytest.mark.parametrize("vram,tier", [(4.0, "low"), (5.9, "low"), (6.0, "mid"),
                                       (11.9, "mid"), (12.0, "high"), (24.0, "high")])
def test_vram_maps_to_tier(vram, tier):
    assert model_profile.resolve_model_profile(installed=[], vram_gb=vram)["tier"] == tier


def test_unknown_vram_uses_low_tier(monkeypatch):
    monkeypatch.setattr(model_profile, "_detect_vram",
                        lambda: {"gb": None, "source": "unknown"})
    profile = model_profile.resolve_model_profile(installed=[])
    assert profile["tier"] == "low"
    assert profile["vram_gb"] is None


def test_low_tier_prefers_installed_1_5b():
    profile = model_profile.resolve_model_profile(
        installed=["qwen2.5:0.5b", "qwen2.5:1.5b-instruct", "qwen2.5:3b-instruct"], vram_gb=4.0)
    assert profile["model"] == "qwen2.5:1.5b-instruct"
    assert profile["source"] == "installed"
    assert profile["warning"] is None
    assert profile["preferred_model"] == "qwen2.5:1.5b-instruct"


def test_low_tier_accepts_implicit_latest_tag():
    profile = model_profile.resolve_model_profile(
        installed=["qwen2.5:1.5b-instruct:latest"], vram_gb=4.0)
    assert profile["model"] == "qwen2.5:1.5b-instruct"


def test_low_tier_falls_back_to_installed_smaller_model():
    profile = model_profile.resolve_model_profile(installed=["qwen2.5:0.5b"], vram_gb=4.0)
    assert profile["model"] == "qwen2.5:0.5b"
    assert profile["warning"] == "preferred_model_missing"
    assert profile["pull_hint"] == "ollama pull qwen2.5:1.5b-instruct"


def test_mid_tier_uses_7b_when_it_fits_and_is_installed():
    profile = model_profile.resolve_model_profile(
        installed=["qwen2.5:7b-instruct", "qwen2.5:3b-instruct"], vram_gb=8.0)
    assert profile["tier"] == "mid"
    assert profile["model"] == "qwen2.5:7b-instruct"
    assert profile["warning"] is None


def test_mid_tier_falls_back_to_installed_3b():
    profile = model_profile.resolve_model_profile(
        installed=["qwen2.5:3b-instruct", "qwen2.5:1.5b-instruct"], vram_gb=8.0)
    assert profile["model"] == "qwen2.5:3b-instruct"
    assert profile["warning"] == "preferred_model_missing"
    assert profile["pull_hint"] == "ollama pull qwen2.5:7b-instruct"


def test_high_tier_uses_14b_when_it_fits():
    profile = model_profile.resolve_model_profile(
        installed=["qwen2.5:14b-instruct", "qwen2.5:7b-instruct"], vram_gb=16.0)
    assert profile["tier"] == "high"
    assert profile["model"] == "qwen2.5:14b-instruct"


def test_model_too_large_for_gpu_is_never_selected_automatically():
    profile = model_profile.resolve_model_profile(installed=["qwen2.5:7b-instruct"], vram_gb=4.0)
    assert profile["model"] == "qwen2.5:1.5b-instruct"
    assert profile["warning"] == "preferred_model_missing"


def test_candidates_and_thinking_models_are_not_auto_selected():
    profile = model_profile.resolve_model_profile(
        installed=["dusnx-vi-v3-20261107:latest", "qwen3:4b", "smollm:135m"], vram_gb=4.0)
    assert profile["model"] == "qwen2.5:1.5b-instruct"
    assert profile["source"] == "unavailable"


def test_forced_low_profile_does_not_load_a_large_model(monkeypatch):
    monkeypatch.setenv("DUSNX_MODEL_PROFILE", "low")
    profile = model_profile.resolve_model_profile(
        installed=["qwen2.5:14b-instruct", "qwen2.5:1.5b-instruct"], vram_gb=16.0)
    assert profile["model"] == "qwen2.5:1.5b-instruct"

    profile = model_profile.resolve_model_profile(installed=["qwen2.5:14b-instruct"], vram_gb=16.0)
    assert profile["model"] == "qwen2.5:1.5b-instruct"
    assert profile["source"] == "unavailable"
    assert profile["warning"] == "preferred_model_missing"


def test_explicit_model_wins_over_auto(monkeypatch):
    monkeypatch.setenv("DUSNX_OLLAMA_MODEL", "qwen2.5:3b-instruct")
    profile = model_profile.resolve_model_profile(installed=["qwen2.5:1.5b-instruct"], vram_gb=4.0)
    assert profile["model"] == "qwen2.5:3b-instruct"
    assert profile["source"] == "env"


def test_forced_profile_overrides_detected_tier(monkeypatch):
    profile = model_profile.resolve_model_profile(
        installed=["qwen2.5:1.5b-instruct", "qwen2.5:7b-instruct"], vram_gb=16.0)
    assert profile["tier"] == "high"

    monkeypatch.setenv("DUSNX_MODEL_PROFILE", "mid")
    profile = model_profile.resolve_model_profile(
        installed=["qwen2.5:1.5b-instruct", "qwen2.5:7b-instruct"], vram_gb=16.0)
    assert profile["tier"] == "mid"
    assert profile["model"] == "qwen2.5:7b-instruct"


def test_vram_env_override_is_used(monkeypatch):
    monkeypatch.setenv("DUSNX_MODEL_VRAM_GB", "12")
    profile = model_profile.resolve_model_profile(installed=[])
    assert profile["vram_gb"] == 12.0
    assert profile["vram_source"] == "env"
    assert profile["tier"] == "high"


def test_provider_health_exposes_profile(monkeypatch):
    monkeypatch.setenv("DUSNX_MODEL_VRAM_GB", "4")
    monkeypatch.setattr(provider.urllib.request, "urlopen", lambda *args, **kwargs:
                        io.BytesIO(json.dumps({"models": [{"name": "qwen2.5:1.5b-instruct"},
                                                          {"name": "qwen2.5:3b-instruct"}]}).encode()))
    health = provider.check_ollama_health()
    assert health["configured_model"] == "qwen2.5:1.5b-instruct"
    assert health["model_profile"]["tier"] == "low"
    assert health["model_profile"]["vram_gb"] == 4.0
    assert health["available"] is True
