from __future__ import annotations

import base64
from io import BytesIO

import pytest
from fastapi.testclient import TestClient
from pptx import Presentation
from pptx.enum.chart import XL_CHART_TYPE

from apps.ai_api.main import app
import apps.ai_api.auth as auth_mod
import apps.ai_api.memory as mem_mod
from apps.ai_api.office_charts import (
    MAX_POINTS,
    build_chart_slide,
    validate_chart_request,
)


@pytest.fixture(autouse=True)
def isolated_env(tmp_path, monkeypatch):
    monkeypatch.setenv("DUSNX_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("DUSNX_PROVIDER", "mock")
    modules = (auth_mod, mem_mod)
    for module in modules:
        for name in ("_auth_db", "_memory_db"):
            db = getattr(module, name, None)
            if db is not None:
                db.close()
                setattr(module, name, None)
    yield
    for module in modules:
        for name in ("_auth_db", "_memory_db"):
            db = getattr(module, name, None)
            if db is not None:
                db.close()
                setattr(module, name, None)


def _chart_counts(payload: bytes):
    presentation = Presentation(BytesIO(payload))
    charts = [shape for shape in presentation.slides[0].shapes if getattr(shape, "has_chart", False)]
    assert len(presentation.slides) == 1
    assert len(charts) == 1
    chart = charts[0].chart
    return chart, list(chart.plots[0].categories), list(chart.series[0].values)


def test_builds_editable_chart_for_each_type():
    for chart_type, expected in (("bar", XL_CHART_TYPE.COLUMN_CLUSTERED),
                                 ("line", XL_CHART_TYPE.LINE_MARKERS),
                                 ("pie", XL_CHART_TYPE.PIE)):
        chart, categories, values = _chart_counts(
            build_chart_slide("Doanh thu theo quý", chart_type, ["Q1", "Q2", "Q3"], [12.5, 18, 9.75]))
        assert chart.chart_type == expected
        assert categories == ["Q1", "Q2", "Q3"]
        assert values == [12.5, 18, 9.75]


def test_validation_rejects_unsafe_or_mismatched_rows():
    assert validate_chart_request(" T ", "bar", ["A", "B"], [1, 2]) == ("T", "bar", ["A", "B"], [1.0, 2.0])
    bad = [
        ("", "bar", ["A", "B"], [1, 2]),
        ("T", "radar", ["A", "B"], [1, 2]),
        ("T", "bar", ["A"], [1]),
        ("T", "bar", ["A", "B"] * (MAX_POINTS // 2 + 1), [1] * (MAX_POINTS + 2)),
        ("T", "bar", ["A", "B"], [1]),
        ("T", "bar", ["A", "B"], [1, float("nan")]),
        ("T", "bar", ["A", "B"], [1, True]),
        ("T", "bar", ["A", "\u0000"], [1, 2]),
        ("T", "bar", ["A" * 61, "B"], [1, 2]),
    ]
    for args in bad:
        with pytest.raises(ValueError):
            validate_chart_request(*args)


def test_chart_endpoint_requires_auth_and_returns_a_native_chart():
    with TestClient(app) as client:
        assert client.post("/v1/office/chart-slide", json={
            "title": "T", "chart_type": "bar", "labels": ["A", "B"], "values": [1, 2]}).status_code == 401
        assert client.post("/v1/auth/register", json={"username": "chartuser", "password": "secret12345"}).status_code == 201
        token = client.post("/v1/auth/login", json={"username": "chartuser", "password": "secret12345"}).json()["token"]
        headers = {"Authorization": f"Bearer {token}"}

        response = client.post("/v1/office/chart-slide", headers=headers, json={
            "title": "Doanh thu theo quý", "chart_type": "line",
            "labels": ["Q1", "Q2", "Q3"], "values": [12.5, 18, 9.75]})
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["slide_count"] == 1
        assert body["chart_type"] == "line"
        assert body["categories"] == 3
        payload = base64.b64decode(body["file_base64"])
        assert len(payload) == body["bytes"]
        chart, categories, values = _chart_counts(payload)
        assert chart.chart_type == XL_CHART_TYPE.LINE_MARKERS
        assert categories == ["Q1", "Q2", "Q3"]
        assert values == [12.5, 18, 9.75]

        assert client.post("/v1/office/chart-slide", headers=headers, json={
            "title": "T", "chart_type": "bar", "labels": ["A", "B"], "values": [1]}).status_code == 400
