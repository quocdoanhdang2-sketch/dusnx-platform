"""Regression tests for verification harness contracts, summary calculation, and safety guards."""
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from verify_bilingual_generation import evaluate_text_language, compute_bilingual_summary, assess_completion, evaluate_case_output, resolve_token_budget, provider_attempt_metadata, review_model_label
from verify_chat_provenance import provenance_stack_directory
from verify_sqlite_backup_restore import verify_protected_backup_integrity


def test_failed_case_does_not_increment_success():
    cases = {
        "case_1": {
            "case_type": "llm_generation",
            "contract_passed": False,
            "linguistic_status": "divergent",
        },
        "case_2": {
            "case_type": "llm_generation",
            "contract_passed": True,
            "linguistic_status": "matched",
        },
    }
    summary = compute_bilingual_summary(cases)
    assert summary["total_cases"] == 2
    assert summary["contract_passed"] == 1
    assert summary["contract_failed"] == 1
    assert summary["real_llm_generations"] == 1


def test_provider_offline_not_counted_as_generation_or_language_match():
    cases = {
        "case_offline": {
            "case_type": "expected_provider_error",
            "contract_passed": True,
            "linguistic_status": "not_applicable",
        }
    }
    summary = compute_bilingual_summary(cases)
    assert summary["total_cases"] == 1
    assert summary["contract_passed"] == 1
    assert summary["contract_failed"] == 0
    assert summary["real_llm_generations"] == 0
    assert summary["expected_provider_failures"] == 1
    assert summary["eligible_language_cases"] == 0
    assert summary["linguistic_matched"] == 0
    assert summary["linguistic_divergent"] == 0


def test_template_recall_not_in_language_denominator():
    cases = {
        "case_recall": {
            "case_type": "template_recall",
            "contract_passed": True,
            "linguistic_status": "not_applicable",
        }
    }
    summary = compute_bilingual_summary(cases)
    assert summary["template_recalls"] == 1
    assert summary["real_llm_generations"] == 0
    assert summary["eligible_language_cases"] == 0
    assert summary["linguistic_matched"] == 0


def test_provenance_stack_directory_is_unique_per_report_name(tmp_path):
    first = provenance_stack_directory(tmp_path / "provenance-r1.json")
    second = provenance_stack_directory(tmp_path / "provenance-r2.json")
    assert first.parent == second.parent == tmp_path
    assert first != second


def test_metadata_correct_but_output_divergent():
    english_text = "The primary benefit of continuous integration is automated reliability and rapid feedback."
    heur = evaluate_text_language(english_text)
    assert heur["actual_language"] == "en"

    # Suppose expected was 'vi' (cross-lingual prompt limitation)
    expected_lang = "vi"
    actual_lang = heur["actual_language"]
    linguistic_status = "matched" if actual_lang == expected_lang else "divergent"
    assert linguistic_status == "divergent"

    cases = {
        "case_cross": {
            "case_type": "llm_generation",
            "contract_passed": True,
            "linguistic_status": linguistic_status,
        }
    }
    summary = compute_bilingual_summary(cases)
    assert summary["eligible_language_cases"] == 1
    assert summary["linguistic_matched"] == 0
    assert summary["linguistic_divergent"] == 1


def test_language_evaluator_uncertain_does_not_assume_english():
    # Digits and symbols with no linguistic markers
    heur = evaluate_text_language("1234567890 !@#$%^&*()_+")
    assert heur["actual_language"] == "uncertain"
    assert heur["vi_words"] == 0
    assert heur["en_words"] == 0


def test_completion_uses_finish_reason_and_output_shape_not_budget_alone():
    at_budget = assess_completion("A complete answer.", "stop", 512, 512)
    assert at_budget["status"] == "uncertain"
    assert at_budget["reason"] == "token_budget_reached_without_proof_of_truncation"
    assert assess_completion("A complete answer.", "stop", 511, 512)["status"] == "passed"
    limited_complete = assess_completion("A useful short list item", "length", 512, 512)
    assert limited_complete["status"] == "uncertain"
    assert limited_complete["reason"] == "provider_limit_without_clear_truncation"
    assert assess_completion("This helps in", "length", 512, 512)["status"] == "failed"
    assert assess_completion("```python\nprint(1)", "stop", 512, 512)["reason"] == "unclosed_code_fence"


def test_completion_uses_budget_from_actual_provider_attempt_not_harness_default():
    response = {
        "provider_ok": True, "provider_called": True, "response_source": "llm",
        "tokens_generated": 967, "done_reason": "stop",
        "provider_attempts": [{"provider_diagnostics": {"num_predict": 1024}}],
    }
    assert resolve_token_budget(response) == 1024
    completion = evaluate_case_output("Explain a gateway.", "A complete answer.", "en",
        "llm_generation", response)["completion"]
    assert completion["status"] == "passed"
    assert completion["reason"] == "no_provider_limit_or_obvious_open_clause"

    response.update(tokens_generated=1024, done_reason="length")
    completion = evaluate_case_output("Explain a gateway.", "A complete answer.", "en",
        "llm_generation", response)["completion"]
    assert completion["status"] == "uncertain"
    assert completion["token_budget"] == 1024


def test_manual_case_provenance_carries_actual_attempt_budget_even_for_provider_errors():
    response = {
        "provider_called": True, "provider_ok": False, "response_source": "provider_error",
        "done_reason": "length", "provider_attempts": [
            {"attempt": 1, "provider_diagnostics": {"num_predict": 1024, "eval_count": 1024}}
        ],
    }
    metadata = provider_attempt_metadata(response)
    assert metadata["token_budget"] == 1024
    assert metadata["provider_attempts"] == response["provider_attempts"]
    unknown = provider_attempt_metadata({"provider_called": True, "provider_attempts": []})
    assert unknown["token_budget"] is None


def test_review_table_model_label_comes_from_run_configuration():
    assert review_model_label({"configuration": {"expected_model": "qwen3:4b"}}) == "qwen3:4b"
    assert review_model_label({"configuration": {"expected_model": "  "}}) == "unknown model"
    assert review_model_label({}) == "unknown model"


def test_missing_protected_dir_handles_safely_without_keyerror(tmp_path):
    missing_dir = tmp_path / "nonexistent_protected_backup"
    res = verify_protected_backup_integrity(missing_dir)
    assert res["status"] == "skipped"
    assert res["reason"] == "protected_dir_not_found"
    assert "integrity_passed" in res
    assert res["integrity_passed"] is None
