"""Regression coverage for language, entities, context, completion, and strict reporting."""
import json
import secrets
from io import BytesIO
from unittest.mock import patch
import pytest
from fastapi.testclient import TestClient

from apps.ai_api import main, provider
from apps.ai_api.main import app
import apps.ai_api.auth as auth_mod
import apps.ai_api.memory as mem_mod
from apps.ai_api.language import assess_response_language
from scripts.verify_bilingual_generation import (
    assess_completion,
    assess_entity_preservation,
    evaluate_case_output,
    evaluation_exit_code,
    verify_ollama_model_identity,
)


@pytest.fixture
def isolated_quality_environment(tmp_path, monkeypatch):
    monkeypatch.setenv("DUSNX_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("DUSNX_PROVIDER", "mock")
    if auth_mod._auth_db is not None:
        auth_mod._auth_db.close()
        auth_mod._auth_db = None
    if mem_mod._memory_db is not None:
        mem_mod._memory_db.close()
        mem_mod._memory_db = None
    yield
    if auth_mod._auth_db is not None:
        auth_mod._auth_db.close()
        auth_mod._auth_db = None
    if mem_mod._memory_db is not None:
        mem_mod._memory_db.close()
        mem_mod._memory_db = None


@pytest.fixture
def client(isolated_quality_environment):
    with TestClient(app) as test_client:
        yield test_client


def _register_and_login(client, username):
    password = secrets.token_urlsafe(24)
    client.post("/v1/auth/register", json={"username": username, "password": password})
    result = client.post("/v1/auth/login", json={"username": username, "password": password})
    return username, result.json()["token"]


def test_mixed_script_is_not_accepted_as_vietnamese_but_code_and_quotes_are_exempt():
    mixed = "Để làm việc hiệu quả, hãy nghỉ giải lao khi cảm thấy mệt疲倦 rồi quay lại."
    assert assess_response_language(mixed, "vi")["status"] == "mixed"
    quoted = "Trong log có chuỗi “疲倦”; còn hướng dẫn là hãy nghỉ giải lao khi cần."
    assert assess_response_language(quoted, "vi")["status"] == "matched"
    code = "Thiết lập `APP_ENV=production` rồi khởi động dịch vụ."
    assert assess_response_language(code, "vi")["status"] == "matched"
    assert assess_response_language("It's a useful approach. It improves reliability.", "en")["status"] == "matched"
    assert assess_response_language("Dùng ký hiệu π trong công thức.", "vi")["status"] == "matched"


def test_entity_check_discards_prompt_echo_and_detects_similar_key_mutation():
    prompt = "Cấu hình URL https://api.example.net/v1/auth và biến DUSNX_PORT=8088 trong file .env."
    bad = ("URL: https://api.example.net/v1/auth\nVar: DUSNXPRT = 8088\nCâu hỏi: " + prompt)
    result = assess_entity_preservation(prompt, bad)
    assert result["status"] == "mutated"
    assert result["mutated"][0]["actual"] == ["DUSNXPRT=8088"]
    good = "DUSNX_PORT=8088\nURL=https://api.example.net/v1/auth\nĐặt các dòng này trong .env.\n" + prompt
    assert assess_entity_preservation(prompt, good)["status"] == "passed"


def test_entity_variants_keep_query_url_and_punctuation_separate_from_assignments():
    prompt = "Set CACHE_TTL_SECONDS=45; endpoint https://edge.example.org/api/v3?mode=fast, in .env."
    good = "CACHE_TTL_SECONDS=45\nCACHE_ENDPOINT=https://edge.example.org/api/v3?mode=fast\nAdd these lines to the environment file."
    assert assess_entity_preservation(prompt, good)["status"] == "passed"


@pytest.mark.parametrize("answer", [
    "```dotenv\nWEBHOOK_RETRY_LIMIT=7\n```",
    "- `WEBHOOK_RETRY_LIMIT = 7`",
    "export WEBHOOK_RETRY_LIMIT = \"7\" # retries",
])
def test_configuration_rubric_accepts_valid_env_assignment_spelling(answer):
    result = evaluate_case_output(
        "Write an .env setting for WEBHOOK_RETRY_LIMIT=7.", answer, "en",
        "application_formatting", {"provider_ok": True, "provider_called": False,
        "response_source": "application_formatter"}, {"assignments": ["WEBHOOK_RETRY_LIMIT=7"]},
    )
    assert result["task"]["status"] == "passed"
    assert result["transport"]["status"] == "not_applicable"


def test_configuration_rubric_rejects_prompt_echo_and_wrong_assignment_value():
    prompt = "Write .env: CACHE_TTL_SECONDS=45"
    echoed = evaluate_case_output(prompt, prompt, "en", "application_formatting", {},
                                  {"assignments": ["CACHE_TTL_SECONDS=45"]})
    wrong = evaluate_case_output(prompt, "```dotenv\nCACHE_TTL_SECONDS=60\n```", "en",
                                 "application_formatting", {},
                                 {"assignments": ["CACHE_TTL_SECONDS=45"]})
    assert echoed["task"]["status"] == "failed"
    assert wrong["task"]["status"] == "failed"


def test_env_formatter_uses_only_supplied_values_and_reports_application_provenance(monkeypatch):
    monkeypatch.setenv("DUSNX_PROVIDER", "ollama")
    prompt = ('Write a .env file with SERVICE_LABEL="orders api", MAX_RETRIES = 3 and '
              'endpoint https://cfg.example.net/v1/run?mode=fast,.')
    with patch("apps.ai_api.provider._ollama_generate") as model:
        result = provider.generate_response(prompt, [], "chat", response_language="en")
    assert result[0] == (
        "```dotenv\n# Endpoint: https://cfg.example.net/v1/run?mode=fast\n"
        'SERVICE_LABEL="orders api"\nMAX_RETRIES=3\n```\n'
        "Save these lines in the application's `.env` file; the application must read the variables from its environment."
    )
    assert result[1] is True
    assert result.provider_called is False
    assert result.provider_call_count == 0
    assert result.response_source == "application_formatter"
    assert result[2] is None and result[3] is None and result[4] is None
    model.assert_not_called()


@pytest.mark.parametrize("prompt", [
    "Translate this line to English: CACHE_TTL_SECONDS=45 in the .env file.",
    "Summarize the following setting: CACHE_TTL_SECONDS=45 in the .env file.",
    "Write a Python script that creates a .env file with CACHE_TTL_SECONDS=45.",
    "Do not create a .env file; explain CACHE_TTL_SECONDS=45 instead.",
])
def test_env_formatter_does_not_handle_translation_or_summary(prompt, monkeypatch):
    monkeypatch.setenv("DUSNX_PROVIDER", "ollama")
    with patch("apps.ai_api.provider._ollama_generate", return_value=(
        "The requested text is handled. CACHE_TTL_SECONDS=45 remains unchanged.", True, "qwen-test", 10)) as model:
        result = provider.generate_response(prompt, [], "chat", response_language="en")
    assert result.response_source == "llm"
    model.assert_called_once()


def test_env_formatter_asks_for_missing_or_conflicting_values_without_calling_model(monkeypatch):
    monkeypatch.setenv("DUSNX_PROVIDER", "ollama")
    prompts = [
        "Create a .env setting named CACHE_TTL_SECONDS but the value is not decided yet.",
        "Create a .env entry with CACHE_TTL_SECONDS=45 and CACHE_TTL_SECONDS=60.",
    ]
    for index, prompt in enumerate(prompts):
        with patch("apps.ai_api.provider._ollama_generate") as model:
            result = provider.generate_response(prompt, [], "chat", response_language="en")
        assert result.response_source == "application_clarification"
        assert result.provider_called is False
        assert "?" in result[0]
        model.assert_not_called()


def test_web_chat_returns_usable_application_formatted_env_without_claiming_generation(client):
    _, token = _register_and_login(client, "synthetic_env_formatter")
    headers = {"Authorization": f"Bearer {token}"}
    sid = client.post("/v1/sessions", headers=headers, json={}).json()["session_id"]
    response = client.post("/v1/chat", headers=headers, json={
        "session_id": sid,
        "message": "Write a .env setting with API_PORT = 8443 and endpoint https://api.example.net/v1.",
        "preferred_language": "en", "request_id": "env-format-live-contract-001",
    })
    data = response.json()
    assert response.status_code == 200
    assert data["provider_ok"] is True
    assert data["provider_called"] is False
    assert data["provider_call_count"] == 0
    assert data["provider_used"] is None and data["model_used"] is None
    assert data["response_source"] == "application_formatter"
    assert data["answer_source"] == "application_rule"
    assert "API_PORT=8443" in data["reply"]
    history = client.get(f"/v1/sessions/{sid}/messages", headers=headers).json()
    assert [item["role"] for item in history] == ["user", "assistant"]


def test_web_chat_asks_for_env_value_instead_of_inventing_one(client, monkeypatch):
    calls = []
    monkeypatch.setattr(provider, "_ollama_generate", lambda *args: calls.append(args))
    _, token = _register_and_login(client, "synthetic_env_missing")
    headers = {"Authorization": f"Bearer {token}"}
    sid = client.post("/v1/sessions", headers=headers, json={}).json()["session_id"]
    response = client.post("/v1/chat", headers=headers, json={
        "session_id": sid,
        "message": "Create a .env setting named CACHE_TTL_SECONDS, but I have not chosen its value yet.",
        "preferred_language": "en", "request_id": "env-missing-value-001",
    })
    data = response.json()
    assert data["response_source"] == "application_clarification"
    assert data["provider_called"] is False
    assert "?" in data["reply"]
    assert "CACHE_TTL_SECONDS=" not in data["reply"]
    assert calls == []


def test_generation_prompt_preserves_cross_language_task_without_injected_translation_command(monkeypatch):
    monkeypatch.setenv("DUSNX_PROVIDER", "ollama")
    captured = []
    with patch("apps.ai_api.provider._ollama_generate", side_effect=lambda system, user: (
            captured.append((system, user)) or ("An API gateway routes requests.", True, "qwen-test", 8))):
        provider.generate_response("Hãy giải thích ngắn gọn API Gateway.", [], "chat", response_language="en")
    assert "Hãy giải thích ngắn gọn API Gateway." in captured[0][1]
    assert "Respond in English" in captured[0][0]
    assert "Translate and answer" not in captured[0][1]
    assert "without changing its task" in captured[0][1]


def test_topic_shift_prompt_explicitly_anchors_short_followup_to_latest_topic(monkeypatch):
    monkeypatch.setenv("DUSNX_PROVIDER", "ollama")
    captured = []
    history = [
        {"role": "user", "content": "I am learning microservices."},
        {"role": "user", "content": "Switch to a new topic: I am studying public key cryptography."},
    ]
    with patch("apps.ai_api.provider._ollama_generate", side_effect=lambda system, user: (
            captured.append(system) or ("Public key cryptography has risks.", True, "qwen-test", 8))):
        provider.generate_response("What are its risks?", [], "chat", history, response_language="en")
    assert "latest topic" in captured[0]
    assert "name that topic in the first sentence" in captured[0]


def test_predeclared_open_ended_rubric_reports_signals_but_remains_uncertain():
    from scripts.verify_bilingual_generation import run_open_ended_coverage

    rubric = {"kind": "open_ended_coverage", "rubric_id": "ci_benefits_v1", "basis": "test fixture",
              "criteria": [{"id": "early", "terms_any": ["catch bugs early"]}]}
    result = run_open_ended_coverage("CI can catch bugs early.", rubric)
    assert result["status"] == "uncertain"
    assert result["automated_signals"][0]["signal_observed"] is True
    assert result["review_required"] is True


def test_corrective_call_deadline_is_capped_below_gateway_timeout(monkeypatch):
    monkeypatch.setenv("DUSNX_GATEWAY_TIMEOUT", "90")
    monkeypatch.setenv("DUSNX_GENERATION_TIMEOUT_MARGIN", "5")
    monkeypatch.setenv("DUSNX_GENERATION_TOTAL_TIMEOUT", "120")
    assert provider.get_generation_total_timeout() == 85


def test_provider_call_after_deadline_is_not_claimed_as_a_transport_attempt():
    called = []
    result, elapsed, did_call = provider._provider_call_with_deadline(
        lambda *args: called.append(args), "system", "message", 0.0,
    )
    assert called == []
    assert did_call is False
    assert elapsed == 0
    assert result.done_reason is None


def test_corrective_prompt_does_not_repeat_the_failed_model_draft(monkeypatch):
    monkeypatch.setenv("DUSNX_PROVIDER", "ollama")
    monkeypatch.setenv("DUSNX_CAPTURE_RAW_GENERATION", "1")
    failed_draft = "Repeated answer line with enough words to trigger the repetition check.\n" * 3
    prompts = []

    def respond(system, user):
        prompts.append(user)
        if len(prompts) == 1:
            return failed_draft, True, "qwen-test", 30
        return "The answer is concise and complete.", True, "qwen-test", 8

    with patch("apps.ai_api.provider._ollama_generate", side_effect=respond):
        result = provider.generate_response("Explain this briefly.", [], "chat", response_language="en")
    assert result[1] is True
    assert result.provider_call_count == 2
    assert len(result.provider_attempts) == 2
    assert result.provider_attempts[0]["elapsed_ms"] >= 0
    assert result.provider_attempts[1]["elapsed_ms"] >= 0
    assert "Repeated answer line" not in prompts[1]
    assert "Do not quote or copy the failed draft" in prompts[1]


def test_bilingual_harness_pins_exact_ollama_model_digest(monkeypatch):
    digest = "a" * 64

    class Response:
        def raise_for_status(self):
            return None

        def json(self):
            return {"models": [{"name": "dusnx-vi-candidate:latest", "digest": digest,
                                "size": 100, "details": {"parameter_size": "494M",
                                "quantization_level": "F16"}}]}

    monkeypatch.setattr("scripts.verify_bilingual_generation.httpx.get", lambda *args, **kwargs: Response())
    result = verify_ollama_model_identity("dusnx-vi-candidate", digest, "http://ollama.local")
    assert result["name"] == "dusnx-vi-candidate:latest"
    assert result["digest"] == digest
    with pytest.raises(RuntimeError, match="digest_mismatch"):
        verify_ollama_model_identity("dusnx-vi-candidate", "b" * 64, "http://ollama.local")


def test_markdown_wrappers_do_not_mutate_exact_entities():
    prompt = "Use https://hooks.example.net/v2/events and set WEBHOOK_RETRY_LIMIT=7."
    answer = ("Webhook target: `https://hooks.example.net/v2/events`\n"
              "- **WEBHOOK_RETRY_LIMIT=7**\nAdd both values to .env.")
    assert assess_entity_preservation(prompt, answer)["status"] == "passed"


def test_context_and_unknown_product_rubrics_reject_wrong_subject_and_invention():
    metadata = {"provider_ok": True, "provider_called": True, "response_source": "llm"}
    unknown = evaluate_case_output("DUSN-X features?", "DUSN-X provides project analytics.", "en",
        "llm_generation", metadata, {"kind": "unknown_product_clarification"})
    assert unknown["task"]["status"] == "failed"
    wrong_subject = evaluate_case_output("What are its benefits?", "Uptane has several benefits.", "en",
        "llm_generation", metadata, {"kind": "context_subject",
            "subject_terms": ["microservices", "distributed systems"], "forbidden_terms": ["uptane"]})
    assert wrong_subject["task"]["status"] == "failed"
    clarifying = evaluate_case_output("What are its benefits?", "Do you mean microservices or distributed systems?", "en",
        "llm_generation", metadata, {"kind": "context_subject",
            "subject_terms": ["microservices", "distributed systems"], "forbidden_terms": ["uptane"]})
    assert clarifying["task"]["status"] == "uncertain"
    assert clarifying["task"]["review_required"] is True


def test_completion_assessment_uses_finish_reason_and_budget_as_distinct_evidence():
    assert assess_completion("MongoDB", "stop", 1)["status"] == "passed"
    assert assess_completion("```python\nprint(1)\n```", None, 3)["status"] == "passed"
    assert assess_completion("This helps in", "stop", 4)["status"] == "failed"
    assert assess_completion("A complete response", "length", 512)["status"] == "failed"
    uncertain = assess_completion("A response", None, 512)
    assert uncertain["status"] == "uncertain"
    assert "proof_of_truncation" in uncertain["reason"]


def test_ollama_finish_reason_and_configured_token_budget_are_reported(monkeypatch):
    monkeypatch.setenv("DUSNX_OLLAMA_NUM_PREDICT", "640")
    requests = []

    def response(request, timeout):
        requests.append(json.loads(request.data))
        payload = {"done": True, "done_reason": "length", "model": "qwen-test",
                   "message": {"content": "An apparently complete sentence."}, "eval_count": 640}
        return BytesIO(json.dumps(payload).encode())

    monkeypatch.setattr(provider.urllib.request, "urlopen", response)
    result = provider._ollama_generate("system", "user")
    assert result[1:] == (True, "qwen-test", 640)
    assert result.done_reason == "length"
    assert requests[0]["options"]["num_predict"] == 640


def test_generation_prompt_uses_recent_context_without_product_blurb(monkeypatch):
    monkeypatch.setenv("DUSNX_PROVIDER", "ollama")
    captured = []

    def fake(system, user):
        captured.append((system, user))
        return ("Microservices allow independent service deployment.", True, "qwen-test", 12)

    with patch("apps.ai_api.provider._ollama_generate", side_effect=fake):
        provider.generate_response(
            "Can you explain your previous answer about its benefits?", [], "chat",
            [{"role": "user", "content": "I am studying microservices architecture."},
             {"role": "assistant", "content": "Prior generated claim."}],
            response_language="en",
        )
    system, _ = captured[0]
    assert "I am studying microservices architecture" in system
    assert "DUSN-X is an adaptive personalized AI assistant platform" not in system
    assert "not independently verified" in system
    assert "ask a short clarifying question" in system
    assert "Prior assistant output (generated, unverified)" in system


def test_topic_shift_drops_older_user_and_assistant_context(monkeypatch):
    monkeypatch.setenv("DUSNX_PROVIDER", "ollama")
    captured = []
    def fake(system, user):
        captured.append(system)
        return ("Public key cryptography has security risks.", True, "qwen-test", 12)
    history = [
        {"role": "user", "content": "I am learning microservices architecture."},
        {"role": "assistant", "content": "A generated answer about microservices."},
        {"role": "user", "content": "Switch to a new topic: I am studying public key cryptography."},
        {"role": "assistant", "content": "A stale prior answer about microservices."},
    ]
    with patch("apps.ai_api.provider._ollama_generate", side_effect=fake):
        provider.generate_response("What are its risks?", [], "chat", history, response_language="en")
    assert "public key cryptography" in captured[0]
    assert "microservices" not in captured[0]
    assert "stale prior answer" not in captured[0]


def test_complete_new_question_does_not_inherit_old_conversation_context(monkeypatch):
    monkeypatch.setenv("DUSNX_PROVIDER", "ollama")
    captured = []
    with patch("apps.ai_api.provider._ollama_generate",
               side_effect=lambda system, user: (captured.append(system) or "Indexes improve queries.", True, "qwen-test", 8)):
        provider.generate_response("Briefly explain why database indexing improves query performance.", [], "chat",
            [{"role": "user", "content": "I am learning microservices."},
             {"role": "assistant", "content": "Old generated output."}], response_language="en")
    assert "microservices" not in captured[0]
    assert "Old generated output" not in captured[0]


def test_repetition_quality_failure_gets_bounded_correction_and_is_not_saved(client, monkeypatch):
    monkeypatch.setenv("DUSNX_PROVIDER", "ollama")
    calls = []

    def repeated(system, message):
        calls.append(message)
        return ("Repeated line with enough words to count toward this quality failure.\n"
                "Repeated line with enough words to count toward this quality failure.\n"
                "Repeated line with enough words to count toward this quality failure.",
                True, "qwen-test", 40)

    monkeypatch.setattr(provider, "_ollama_generate", repeated)
    _, token = _register_and_login(client, "synthetic_repetition_failure")
    headers = {"Authorization": f"Bearer {token}"}
    sid = client.post("/v1/sessions", headers=headers, json={}).json()["session_id"]
    response = client.post("/v1/chat", headers=headers, json={
        "session_id": sid, "message": "Explain this clearly.", "preferred_language": "en",
        "request_id": "quality-repetition-001",
    })
    data = response.json()
    assert data["provider_ok"] is False
    assert data["response_source"] == "provider_error"
    assert data["quality_status"] == "failed"
    assert data["provider_call_count"] == 2
    assert len(calls) == 2
    messages = client.get(f"/v1/sessions/{sid}/messages", headers=headers).json()
    assert [message["role"] for message in messages] == ["user"]


def test_provider_quality_failure_is_not_saved_as_assistant_message(client, monkeypatch):
    monkeypatch.setenv("DUSNX_PROVIDER", "ollama")
    calls = []

    def wrong(system, message):
        calls.append(message)
        return ("DUSNXPRT=8088\nVar name is shown above.\n" + message,
                True, "qwen-test", 30)

    monkeypatch.setattr(provider, "_ollama_generate", wrong)
    _, token = _register_and_login(client, "synthetic_quality_failure")
    headers = {"Authorization": f"Bearer {token}"}
    sid = client.post("/v1/sessions", headers=headers, json={}).json()["session_id"]
    prompt = "Explain this assignment without reprinting it: DUSNX_PORT=8088."
    response = client.post("/v1/chat", headers=headers, json={
        "session_id": sid, "message": prompt, "preferred_language": "en",
        "request_id": "quality-entity-failure-001",
    })
    assert response.status_code == 200
    data = response.json()
    assert data["provider_ok"] is False, {"data": data, "call_count": len(calls)}
    assert data["response_source"] == "provider_error"
    assert data["quality_status"] == "failed"
    assert data["provider_call_count"] == 2
    assert len(calls) == 2
    messages = client.get(f"/v1/sessions/{sid}/messages", headers=headers).json()
    assert [message["role"] for message in messages] == ["user"]


def test_contextless_ambiguous_followup_requests_clarification(client, monkeypatch):
    calls = []
    monkeypatch.setattr(main, "generate_response", lambda **kwargs: calls.append(kwargs))
    _, token = _register_and_login(client, "synthetic_no_context")
    headers = {"Authorization": f"Bearer {token}"}
    sid = client.post("/v1/sessions", headers=headers, json={}).json()["session_id"]
    response = client.post("/v1/chat", headers=headers, json={
        "session_id": sid, "message": "Ưu điểm là gì?", "request_id": "clarify-no-topic-001",
    })
    assert response.status_code == 200
    assert response.json()["response_source"] == "clarification"
    assert response.json()["provider_called"] is False
    assert calls == []


def test_ambiguous_followup_after_multiple_user_topics_clarifies(client, monkeypatch):
    calls = []
    def capture(**kwargs):
        calls.append(kwargs)
        return provider.ProviderResult("I can help with that topic.", True, "ollama", "qwen-test", 8, called=True)
    monkeypatch.setattr(main, "generate_response", capture)
    _, token = _register_and_login(client, "synthetic_multiple_topics")
    headers = {"Authorization": f"Bearer {token}"}
    sid = client.post("/v1/sessions", headers=headers, json={}).json()["session_id"]
    first = client.post("/v1/chat", headers=headers, json={"session_id": sid,
        "message": "I am learning microservices and distributed systems.", "preferred_language": "en",
        "request_id": "multi-topic-0001"})
    assert first.status_code == 200
    calls.clear()
    followup = client.post("/v1/chat", headers=headers, json={"session_id": sid,
        "message": "Advantages?", "preferred_language": "auto",
        "request_id": "multi-topic-0002"})
    assert first.status_code == followup.status_code == 200
    data = followup.json()
    assert data["response_source"] == "clarification"
    assert data["provider_called"] is False
    assert "which topic" in data["reply"].lower()
    assert calls == []


def test_undocumented_dusnx_feature_question_asks_for_source(client, monkeypatch):
    calls = []
    monkeypatch.setattr(main, "generate_response", lambda **kwargs: calls.append(kwargs))
    _, token = _register_and_login(client, "synthetic_product_question")
    headers = {"Authorization": f"Bearer {token}"}
    sid = client.post("/v1/sessions", headers=headers, json={}).json()["session_id"]
    response = client.post("/v1/chat", headers=headers, json={"session_id": sid,
        "message": "Hệ thống DUSN-X có những tính năng cốt lõi nào?", "preferred_language": "vi",
        "request_id": "product-features-0001"})
    assert response.status_code == 200
    data = response.json()
    assert data["response_source"] == "clarification"
    assert data["provider_called"] is False
    assert "tài liệu" in data["reply"].lower()
    assert calls == []


def test_language_preference_control_turn_does_not_count_as_topic_context(client, monkeypatch):
    monkeypatch.setattr(main, "generate_response", lambda **kwargs: None)
    _, token = _register_and_login(client, "synthetic_control_context")
    headers = {"Authorization": f"Bearer {token}"}
    sid = client.post("/v1/sessions", headers=headers, json={}).json()["session_id"]
    saved = client.post("/v1/chat", headers=headers, json={"session_id": sid,
        "message": "Từ giờ trả lời bằng tiếng Anh nhé", "request_id": "pref-context-0001"})
    assert saved.status_code == 200
    followup = client.post("/v1/chat", headers=headers, json={"session_id": sid,
        "message": "Ưu điểm là gì?", "request_id": "pref-context-0002"})
    assert followup.status_code == 200
    assert followup.json()["response_source"] == "clarification"
    assert followup.json()["response_language"] == "en"


def test_short_followup_inherits_language_from_latest_user_context(client, monkeypatch):
    captured = []
    def generate(**kwargs):
        captured.append(kwargs)
        return provider.ProviderResult("A complete English answer.", True, "ollama", "qwen-test", 8, called=True)
    monkeypatch.setattr(main, "generate_response", generate)
    _, token = _register_and_login(client, "synthetic_context_language")
    headers = {"Authorization": f"Bearer {token}"}
    sid = client.post("/v1/sessions", headers=headers, json={}).json()["session_id"]
    first = client.post("/v1/chat", headers=headers, json={"session_id": sid, "message": "Explain microservices architecture.",
        "request_id": "context-lang-0001"})
    second = client.post("/v1/chat", headers=headers, json={"session_id": sid, "message": "Why?",
        "request_id": "context-lang-0002"})
    assert first.status_code == second.status_code == 200
    assert second.json()["response_language"] == "en"
    assert captured[-1]["session_history"][-1]["content"] == "A complete English answer."


def test_strict_modes_fail_mixed_uncertain_and_execution_failed_summaries():
    base = {"contract_failed": 0, "linguistic_divergent": 0, "linguistic_uncertain": 0,
            "linguistic_mixed": 0, "quality_flagged_cases": 0, "task_failed": 0,
            "task_uncertain": 0, "completion_failed": 0, "completion_uncertain": 0}
    assert evaluation_exit_code({**base, "linguistic_mixed": 1}, strict_language=True) == 1
    assert evaluation_exit_code({**base, "task_uncertain": 1}, strict_quality=True) == 1
    assert evaluation_exit_code({**base, "execution_status": "execution_failed"}) == 1
