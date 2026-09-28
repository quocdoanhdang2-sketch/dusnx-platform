from pathlib import Path
import json
import importlib.util
import re

import pytest

from dusnx_core.personalization_benchmark import PilotStep, read_pilot
from dusnx_core.dataset import read_jsonl

ROOT = Path(__file__).resolve().parents[2]
PILOT = ROOT / "benchmarks/week3_personalization_pilot.jsonl"
runner_spec = importlib.util.spec_from_file_location("pilot_runner", ROOT / "python/scripts/evaluate_personalization.py")
runner = importlib.util.module_from_spec(runner_spec)
runner_spec.loader.exec_module(runner)
run_baseline, score_turn, attribution = runner.run_baseline, runner.score_turn, runner.attribution


def write_rows(tmp_path, rows):
    path = tmp_path / "pilot.jsonl"
    path.write_text("\n".join(json.dumps(r) for r in rows), encoding="utf-8")
    return path


def test_contract_order_duplicate_labels_and_required_fields(tmp_path):
    rows = [r.model_dump() for r in read_pilot(PILOT)[:2]]
    assert len(read_pilot(PILOT)) == 36
    for mutate, match in [
        (lambda r: r[1].update(case_id=r[0]["case_id"]), "duplicate"),
        (lambda r: r.reverse(), "in order"),
        (lambda r: r[0].pop("review_status"), "review_status"),
        (lambda r: r[0].update(expected_agent="invented"), "expected_agent"),
        (lambda r: r[0].update(prior_event_ids=[r[1]["case_id"]]), "preceding"),
        (lambda r: r[0].update(known_feedback_value=0.9), "feedback"),
        (lambda r: r[0].update(review_status="independently_reviewed"), "reviewer"),
    ]:
        copy = json.loads(json.dumps(rows))
        mutate(copy)
        with pytest.raises(ValueError, match=match):
            read_pilot(write_rows(tmp_path, copy))


def test_inputs_hide_labels_and_future_context():
    row = read_pilot(PILOT)[0]
    changed = row.model_copy(update={"gold_active_facts": ["secret future"], "expected_intent": "research",
                                     "target_query": True, "expected_keywords": ["secret"]})
    assert changed.prediction_input() == row.prediction_input()
    assert set(row.prediction_input()) == {"step", "platform", "user_message", "session_id",
                                          "project_id", "event_type", "known_feedback_value"}


def test_baselines_really_call_provider_and_only_see_past_inputs():
    turns = [r.prediction_input() for r in read_pilot(PILOT)[:2]]
    turns[1]["session_id"] = "brand-new"
    seen = []
    def generate(**kwargs):
        seen.append(kwargs)
        return "answer", True, "test", None, None
    run_baseline(turns, generate, static_memory=False)
    assert len(seen) == 2
    assert all(not s["memories"] for s in seen)
    assert seen[1]["session_history"] == []
    seen.clear()
    run_baseline(turns, generate, static_memory=True)
    assert not seen[0]["memories"]
    assert seen[1]["memories"][0]["content"] == turns[0]["user_message"]
    assert seen[1]["session_history"] == []
    assert all("target_query" not in s for s in seen)


def test_recall_regression_missing_fact_is_failure_even_if_retrieved():
    gold = read_pilot(PILOT)[1].model_dump()
    pred = dict(reply="Tôi chưa biết.", provider_ok=True, memories_used=["Dark Mode"])
    metrics, _ = score_turn(gold, pred)
    assert metrics["active_recall"] is False
    assert metrics["final_answer_success"] is False
    pred.update(reply="Dark Mode", provider_ok=False)
    assert score_turn(gold, pred)[0]["final_answer_success"] is False
    pred["provider_ok"] = True
    assert score_turn(gold, pred)[0]["final_answer_success"] is True
    assert metrics["obsolete_elimination"] is None


def test_route_scores_agent_action_separately_and_unknown_is_not_model():
    gold = read_pilot(PILOT)[0].model_dump()
    pred = dict(reply="", provider_ok=True, predicted_intent=gold["expected_intent"],
                predicted_agent="wrong", predicted_next_action="wrong")
    metrics, _ = score_turn(gold, pred)
    assert metrics["intent"] is True
    assert metrics["agent"] is False and metrics["action"] is False
    assert attribution("business_rule_override") == "rule"
    assert attribution("event") == "unknown"
    assert attribution("model") == "model"


def test_pilot_cannot_be_train_data_and_does_not_match_synthetic_templates():
    with pytest.raises(ValueError, match="must not be used as training"):
        read_jsonl(PILOT)
    spec = importlib.util.spec_from_file_location("synthetic", ROOT / "python/scripts/generate_synthetic.py")
    generator = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(generator)
    patterns = [re.compile("^" + re.escape(t).replace(re.escape("{topic}"), ".+") + "$", re.I)
                for templates in generator.TEMPLATES.values() for t in templates]
    assert not [(r.case_id, p.pattern) for r in read_pilot(PILOT) for p in patterns if p.fullmatch(r.user_message)]
    for config in (ROOT / "configs").glob("*.yaml"):
        assert "benchmarks/" not in config.read_text(encoding="utf-8")


def test_original_routing_benchmark_rejects_out_of_order():
    from dusnx_core.benchmark import read_benchmark, validate_benchmark, BenchmarkValidationError
    rows = read_benchmark(ROOT / "python/tests/fixtures/benchmark_v1_fixture.jsonl")
    with pytest.raises(BenchmarkValidationError, match="continuous"):
        validate_benchmark(list(reversed(rows)))


def test_real_app_runner_confirmed_memory_survives_new_session(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient
    import apps.ai_api.main as main_mod
    import apps.ai_api.auth as auth_mod
    import apps.ai_api.memory as mem_mod
    def close():
        for mod, attr in ((auth_mod, "_auth_db"), (mem_mod, "_memory_db")):
            db = getattr(mod, attr)
            if db:
                db.close()
            setattr(mod, attr, None)
    close()
    monkeypatch.setenv("DUSNX_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("DUSNX_PROVIDER", "mock")
    steps = [r for r in read_pilot(PILOT) if r.sequence_id == "case_02_modify_decision_confirm"]
    inputs = [r.prediction_input() for r in steps]
    inputs[-1]["session_id"] = "new-session"
    try:
        with TestClient(main_mod.app) as client:
            predictions = runner.run_dusnx(inputs, client, main_mod)
            assert len(predictions) == 4
            assert predictions[1]["predicted_next_action"] == "await_confirm"
            assert predictions[2]["predicted_intent"] == "decision_update"
            assert predictions[2]["decision_source"] == "rule"
            final = predictions[-1]
            assert "MongoDB" in final["reply"] and "PostgreSQL" not in final["reply"]
            assert any("cơ sở dữ liệu" in m for m in final["active_memories"])
            assert final["state_version"] == 4
            # Fresh account on a second replay cannot inherit state/memory.
            second = runner.run_dusnx([inputs[-1]], client, main_mod)
            assert second[0]["active_memories"] == []
            assert second[0]["state_version"] == 1
    finally:
        close()
