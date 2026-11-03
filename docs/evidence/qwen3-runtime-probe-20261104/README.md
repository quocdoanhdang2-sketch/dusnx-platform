# Qwen3/Ollama paired template probe (2026-11-04)

This is a new, synthetic-only evidence package. It records direct calls to local Ollama `/api/chat`; it is **not** a Gateway, FastAPI, Chromium, application, or acceptance-quality run. It does not claim human review. All prompts and outputs were synthetic. Thinking text was never saved; only its character count and SHA-256 are present.

## Code and environment

- Repository: `quocdoanhdang2-sketch/dusnx-platform`.
- Probe ran on quality branch code SHA `ccbad152f600eba97349ca8a7b11d1c8a03e1f80`, before the diagnostic code commit `e89e57467fde95ed11d077033ecfbc23a30b7ff3` and this evidence commit. Do not attribute probe runs to later code.
- Ollama `0.40.14`; local endpoint `http://127.0.0.1:11434`.
- Base: `qwen3:4b`, digest `359d7dd4bcdab3d86b87d73ac27966f4dbb9f5efdfcc75d34a8764a09474fae7`, Q4_K_M, 4.0B.
- Isolated candidate: `dusnx-qwen3-4b-no-think-template-probe-20261104:latest`, digest `b8a53a0db98c2ea8d910b367482828188e7cab1724e9faa72e2d11582009d0d8`, same base weights/quantization, template-only change described in `candidate-template-metadata.json`. It was a local probe tag and was not promoted or made the application default.
- API `/api/show` for the base tag advertised `thinking.values=[true]`, default true. No API `think` field was sent. The probe that removes the final `<think>` prefix is explicitly a custom template experiment, not a supported API non-thinking mode.
- Both models received the same prompts, system task, temperature `0.1`, repeat penalty `1.25`, repeat_last_n `64`, context `4096`, timeout `65s`, stream false and keep_alive `5m`. API Gateway English was repeated twice at budgets 512 and 1024; entity-preserving translation and Vietnamese Gateway benefit were each run once at budget 512, first on base then candidate.
- GPU observed: RTX 3050 Laptop, 4 GB; loaded model reported ~2.34 GB VRAM. CPU/RAM telemetry was unavailable in the local process context. Warm/cold is not separately randomized; the first trial includes model load (~8.3 s), later base trials report 7–15 ms load time.

## Observed results

| Model/config | API Gateway EN, budget 512 | API Gateway EN, budget 1024 | Translate URL + KEY=VALUE, budget 512 | Gateway benefit VI, budget 512 |
| --- | --- | --- | --- | --- |
| Base Qwen3 | 2/2 HTTP 200, `stop`, non-empty content; 12.3–19.6 s | 2/2 HTTP 200, `stop`, non-empty content; 19.9–24.1 s | HTTP 200, `length`, 512 eval tokens, content empty, thinking 2018 chars, 25.7 s | HTTP 200, `length`, 512 eval tokens, content empty, thinking 2783 chars, 26.9 s |
| Custom-template candidate | 2/2 HTTP 200, `stop`, non-empty content; thinking remained present | 2/2 HTTP 200, `stop`, non-empty content; thinking remained present | HTTP 200, `length`, 512 eval tokens, content empty, thinking 2114 chars, 26.6 s | HTTP 200, `length`, 512 eval tokens, content empty, thinking 2602 chars, 28.0 s |

The content of all six non-empty API Gateway answers is preserved in the JSON. They directly explain request routing/security at an API entry point and are not a broad factual-quality score. Both translation and Vietnamese representative tasks returned no user-facing content for both tags. The candidate still emitted thinking, so removing the template prefix did not turn reasoning off and did not resolve the empty-content failures. Do not enable this candidate by default.

The historical 1024-token Gateway failures and timeout in `docs/evidence/qwen3-invalid-schema-followup-20261104/` remain relevant: increasing the budget reduces some empty-content cases but is not a reliable fix and can approach the 60-second app per-attempt timeout. The paired direct probe did not exercise application timeout/retry or state mutation.

## Command and test provenance

- Probe source: `run-paired-probe.py`. Invocation: `python -m py_compile runtime/qwen3-template-probe-20261104/run-paired-probe.py`, then `python runtime/qwen3-template-probe-20261104/run-paired-probe.py` from the repository root. The JSON reports all 12 trials and `execution_status=completed`; the shell exit code was not captured and is recorded as `unknown` in the manifest.
- Focused regression on the quality branch after the diagnostic change: `python/.venv/Scripts/python.exe -m pytest python/tests/test_week4_integration.py python/tests/test_response_quality.py -q --tb=short -p no:cacheprovider --basetemp runtime/pytest-qwen-diagnostics-20261104-r3`; **56 passed**, exit 0. The tracked code tree was then committed as `e89e57467fde95ed11d077033ecfbc23a30b7ff3`; no code changed between that test and commit.
- Independent diagnostic-only implementation was applied to an isolated worktree at main SHA `7980e71350d9c3512aff897af3a1fa7fc13982df`; `python/.venv/Scripts/python.exe -m pytest runtime/main-provider-diagnostic-check-20261104/python/tests/test_week4_integration.py -q --tb=short -p no:cacheprovider --basetemp runtime/pytest-main-provider-20261104` reported **15 passed**, exit 0. It was committed/pushed on review branch SHA `965c544f604691fee0e71a8fbd28b85946f47277`, PR #4, merged as `953d62efa5bf874b9852f6a02fcb7844258ec317`.
- Full Python suite on exact quality SHA `e89e57467fde95ed11d077033ecfbc23a30b7ff3`: `python/.venv/Scripts/python.exe -m pytest python/tests -q --tb=short -p no:cacheprovider --basetemp runtime/pytest-full-qwen-diagnostics-20261104`; **303 passed**, exit 0. Output is preserved in `full-pytest-output.txt`.
- During fixture correction, one intermediate focused run was `55 passed, 1 failed`: its fixture had `eval_count=512` but asserted `token_budget_status=not_reached`. The expectation was corrected to `reached`; the complete affected suite was rerun and passed 56/56.
- No Node, .NET, PowerShell health, Gateway, browser/runtime, memory/backup harness, or strict bilingual run was executed in this turn. Existing historical runs are not recast as new verification. Main CI run for PR head `965c544f604691fee0e71a8fbd28b85946f47277` is reported success; no workflow run/status was returned for merged main SHA `953d62efa5bf874b9852f6a02fcb7844258ec317` at evidence packaging time.

## Limits and next action

This probe proves the observed response shape and that the template-only change is ineffective for these two budget-exhausted examples. It does not establish that every Qwen3 task fails, nor that the custom template is generally worse. Before considering any model/default/config change, the remaining work is a supported, repeatable transport/content path on actual Gateway requests, followed by the strict task/context/entity/language suite and review of every failed/uncertain case. Model defaults remain unchanged.
