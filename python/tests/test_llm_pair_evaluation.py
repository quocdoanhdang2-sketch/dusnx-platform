import importlib.util
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "evaluate_llm_pair.py"
SPEC = importlib.util.spec_from_file_location("evaluate_llm_pair", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def test_completion_cases_includes_each_assistant_turn_with_prior_context():
    row = {
        "id": "test-sequence-01",
        "messages": [
            {"role": "system", "content": "Answer in Vietnamese."},
            {"role": "user", "content": "Question one?"},
            {"role": "assistant", "content": "Answer one."},
            {"role": "user", "content": "Follow-up question?"},
            {"role": "assistant", "content": "Answer two."},
        ],
        "quality_contracts": [
            {"required_facts": ["fact one"], "forbidden_facts": [], "response_mode": "answer"},
            {"required_facts": ["fact two"], "forbidden_facts": [], "response_mode": "answer"},
        ],
    }

    cases = MODULE.completion_cases([row])

    assert len(cases) == 2
    assert [case["id"] for case in cases] == ["test-sequence-01:1", "test-sequence-01:2"]
    assert cases[0]["messages"][-1]["content"] == "Question one?"
    assert cases[0]["reference"] == "Answer one."
    assert cases[1]["messages"][-2]["content"] == "Answer one."
    assert cases[1]["messages"][-1]["content"] == "Follow-up question?"
    assert cases[1]["reference"] == "Answer two."
    assert cases[1]["quality_contracts"][0]["required_facts"] == ["fact two"]


def test_completion_cases_rejects_contract_count_mismatch():
    row = {
        "id": "test-sequence-02",
        "messages": [
            {"role": "system", "content": "Answer in Vietnamese."},
            {"role": "user", "content": "Question?"},
            {"role": "assistant", "content": "Answer."},
        ],
        "quality_contracts": [],
    }

    try:
        MODULE.completion_cases([row])
    except ValueError as exc:
        assert "Quality contract count mismatch" in str(exc)
    else:
        raise AssertionError("Expected contract mismatch to be rejected")
