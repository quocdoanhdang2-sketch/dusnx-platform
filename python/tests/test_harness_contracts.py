"""Regression tests for verification harness contracts, summary calculation, and safety guards."""
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from verify_bilingual_generation import evaluate_text_language, compute_bilingual_summary
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


def test_missing_protected_dir_handles_safely_without_keyerror(tmp_path):
    missing_dir = tmp_path / "nonexistent_protected_backup"
    res = verify_protected_backup_integrity(missing_dir)
    assert res["status"] == "skipped"
    assert res["reason"] == "protected_dir_not_found"
    assert "integrity_passed" in res
    assert res["integrity_passed"] is None
