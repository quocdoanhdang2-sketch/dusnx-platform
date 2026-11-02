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
