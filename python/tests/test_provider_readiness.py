"""Separate an offline service from a running service without the configured model."""
import io
import json
import urllib.error

import pytest

from apps.ai_api import provider


@pytest.mark.parametrize("models,available", [([], False), (["different:latest"], False),
                                              (["qwen2.5:0.5b"], True)])
def test_ollama_readiness_reports_missing_model(monkeypatch, models, available):
    monkeypatch.setenv("DUSNX_OLLAMA_MODEL", "qwen2.5:0.5b")
    monkeypatch.setattr(provider.urllib.request, "urlopen", lambda *args, **kwargs:
                        io.BytesIO(json.dumps({"models": [{"name": name} for name in models]}).encode()))
    health = provider.check_ollama_health()
    assert health["reachable"] is True
    assert health["available"] is available
    assert health["model_available"] is available
    assert health.get("error") == (None if available else "model_missing")


def test_ollama_readiness_reports_offline_service(monkeypatch):
    def offline(*args, **kwargs):
        raise urllib.error.URLError("synthetic connection refused")
    monkeypatch.setattr(provider.urllib.request, "urlopen", offline)
    health = provider.check_ollama_health()
    assert health["reachable"] is False
    assert health["available"] is False
    assert health["error"] == "unreachable"


def test_ollama_readiness_accepts_only_the_implicit_latest_tag(monkeypatch):
    monkeypatch.setenv("DUSNX_OLLAMA_MODEL", "dusnx-vi-candidate")
    monkeypatch.setattr(provider.urllib.request, "urlopen", lambda *args, **kwargs:
                        io.BytesIO(json.dumps({"models": [{"name": "dusnx-vi-candidate:latest"}]}).encode()))
    health = provider.check_ollama_health()
    assert health["model_available"] is True
    assert health["configured_model"] == "dusnx-vi-candidate"

    monkeypatch.setenv("DUSNX_OLLAMA_MODEL", "dusnx-vi-candidate:1.0")
    health = provider.check_ollama_health()
    assert health["model_available"] is False


def test_openai_health_matches_models_prefixed_ids(monkeypatch):
    """Gemini's OpenAI-compatible /models lists "models/<id>"; that must still count as available."""
    monkeypatch.setenv("DUSNX_PROVIDER", "openai")
    monkeypatch.setattr(provider, "OPENAI_API_KEY", "synthetic-key")
    monkeypatch.setattr(provider, "OPENAI_MODEL", "gemini-3.1-flash-lite")
    monkeypatch.setattr(provider.urllib.request, "urlopen", lambda *args, **kwargs:
                        io.BytesIO(json.dumps({"data": [
                            {"id": "models/gemini-2.5-flash"},
                            {"id": "models/gemini-3.1-flash-lite"},
                        ]}).encode()))
    health = provider.get_provider_health()
    assert health["reachable"] is True
    assert health["available"] is True
    assert health["model_available"] is True
    assert health["status"] == "ok"


def test_openai_health_reports_unlisted_models(monkeypatch):
    monkeypatch.setenv("DUSNX_PROVIDER", "openai")
    monkeypatch.setattr(provider, "OPENAI_API_KEY", "synthetic-key")
    monkeypatch.setattr(provider, "OPENAI_MODEL", "missing-model")
    monkeypatch.setattr(provider.urllib.request, "urlopen", lambda *args, **kwargs:
                        io.BytesIO(json.dumps({"data": [{"id": "models/gemini-2.5-flash"}]}).encode()))
    health = provider.get_provider_health()
    assert health["reachable"] is True
    assert health["available"] is False
    assert health["status"] == "model_not_listed"
