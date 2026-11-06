# Qwen3/Ollama runtime and quality follow-up evidence (2026-11-04)

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

## Live Gateway and model observations

- An isolated local stack ran on `8117` (FastAPI) and `8187` (Gateway), using the fresh synthetic DBs under `runtime/quality-gateway-probe-20261104/`, the existing checkpoint SHA-256 `56f56e6d61afc264fb02d690d2872fb3ac5db9749a659c8493fd9d99eab7e7b1`, and explicit local test model `qwen3:4b`. Tested application code SHA: `e89e57467fde95ed11d077033ecfbc23a30b7ff3`. No user DB, model, or checkpoint was altered.
- Chat provenance report: exit `1`, status `provider_quality_rejected`. Authentication, synthetic memory and provider/model identity were correct. The one generated request returned HTTP 200, `done=true`, `done_reason=length`, `eval_count=512/512`, empty content, 2,174 thinking characters and 37.281 seconds. Provider source was `provider_error`; language/task were not scored as successful.
- Strict bilingual Gateway run: **27 cases, exit 1**. Contract 16/27; 11 contract failures. Ten normal generation requests across the listed cases and User B in the two-user isolation case returned `empty_content` with `done_reason=length` at 512 tokens. The failed IDs are `CASE_03_VI_PREF_EN`, `CASE_04_EN_PREF_VI`, `CASE_05_AUTO_VI`, `VARIANT_21_TOPIC_SHIFT_ECC_FOLLOWUP`, `VARIANT_22_CROSS_LANGUAGE_GATEWAY_BENEFIT`, `VARIANT_23_TOPIC_SHIFT_TLS_FOLLOWUP`, `VARIANT_25_TRANSLATE_PRESERVE_LITERAL`, `VARIANT_27_HTTP_IDEMPOTENCY_EXPLANATION`, `VARIANT_16_TOPIC_SHIFT_FOLLOWUP`, `CASE_10_DURABLE_MEMORY_PREF_CHANGE`, and User B of `CASE_11_TWO_USERS_LANGUAGE_ISOLATION`. User A returned English; User B had no answer, so the case does not establish a cross-user leak.
- Four successful task generations were `CASE_02_EN_PREF_EN`, `CASE_06_AUTO_EN`, `VARIANT_24_ECC_STANDARD_USE`, and `VARIANT_26_CROSS_LANGUAGE_PASSWORD_SALT`. All four matched the expected language and finished with `stop`; each task remains `uncertain` because there was no independent human review. Language agreement is not a factual-quality pass.
- On the same two synthetic direct tasks, Qwen3 at budget 1024 translated the URL/assignment sentence with empty content in **2/2** trials at 60.08?60.89 seconds. It answered the Vietnamese API Gateway benefit in **2/2** trials with concise, relevant answers in 45.24?46.91 seconds. This may help that task, but does not fix translation and is too close to the app's 60-second provider timeout to promote as a global retry/default.
- Four direct trials on the existing default `qwen2.5:0.5b` (digest `a8b0c51577010a279d933d14c2a8ab4b268079d44c5c8830c0a93900f1827c67`) returned `stop` and non-empty content in 0.19?1.70 seconds. Its translation output remained Vietnamese (task failure); its two Gateway-benefit answers were long and repeated multiple unsupported-sounding claims. These are observed outputs, not independent semantic ratings. This small comparison does not show that either model meets task-quality gates or justify changing the default.

## Runtime checks and command provenance

All live application and browser prompts/accounts were synthetic. No raw thinking was stored. The full per-attempt JSON reports distinguish raw answer, sanitized output, provider metadata and thinking lengths/hashes.

- Direct paired Qwen3/template probe ran on code SHA `ccbad152f600eba97349ca8a7b11d1c8a03e1f80`; it completed 12 trials. Direct budget-1024 Qwen3 and Qwen2.5 baseline probes each completed four trials. Native probe command exit codes were not captured (`unknown`); each JSON records completed trial counts and timings.
- Live Qwen3 provenance command: `python/.venv/Scripts/python.exe scripts/verify_chat_provenance.py --gateway http://127.0.0.1:8187 --output runtime/quality-gateway-probe-20261104/chat-provenance-r1.json --expected-model qwen3:4b --expected-model-digest 359d7dd4bcdab3d86b87d73ac27966f4dbb9f5efdfcc75d34a8764a09474fae7`; **exit 1**, `provider_quality_rejected`.
- Strict bilingual command used that Gateway, `--expected-model qwen3:4b`, its exact digest, `--strict-language --strict-quality`, and output directory `runtime/quality-gateway-probe-20261104/bilingual-strict-r1`; **exit 1**, 27/27 cases completed. Historical output is retained unchanged.
- Browser command: `python/.venv/Scripts/python.exe scripts/verify_week4_web.py --spawn-stack --output-dir runtime/quality-gateway-probe-20261104/browser-r1`; **exit 0**, eight checks passed, including Chromium auth/history/retry/XSS/mobile and one real Ollama call using the default `qwen2.5:0.5b`. This is a Web/runtime check, not a broad model-quality pass.
- Memory reliability command: `python/.venv/Scripts/python.exe scripts/verify_memory_reliability.py --output-dir runtime/quality-gateway-probe-20261104/memory-reliability-r1`; **exit 0**, ten HTTP/Chromium/SQLite checks passed on isolated synthetic DBs. Provider-offline tests are fault injection, not generation.
- SQLite backup/restore command used `--output-dir runtime/quality-gateway-probe-20261104/sqlite-backup-r1` and a deliberately nonexistent protected directory under `runtime/`; **exit 0**. Synthetic level 1 passed: 205 history entries restored in order across three pages, auth, memory supersession and retry idempotency. Protected backup inspection was skipped; no personal backup was opened.
- Full pytest on quality SHA `e89e57467fde95ed11d077033ecfbc23a30b7ff3`: **303 passed**, exit 0. After the reporter fix, full pytest on exact code SHA `e8be1f593a49eab81c5dc3bd8f046a0c08ca46b5`: **304 passed**, exit 0; focused harness/quality tests: **52 passed**, exit 0.
- Node Web/auth/Office mock: **26 passed**, exit 0. .NET Release Gateway build: **0 warnings, 0 errors**, exit 0; Gateway history tests: **7/7**, exit 0. PowerShell local health tests: **6/6**, exit 0.
- The earlier first focused pytest attempt hit Windows temp-directory access errors; it was retried with a fresh workspace basetemp and elevated workspace permissions. One intermediate test run had 55 passed/1 failed because a fixture asserted `not_reached` for `eval_count=512`; the expectation was corrected to `reached`, then focused and full suites passed.
- Local main before/after: `7980e71350d9c3512aff897af3a1fa7fc13982df` -> `953d62efa5bf874b9852f6a02fcb7844258ec317`. PR #4's diagnostic-only head `965c544f604691fee0e71a8fbd28b85946f47277` had a successful Actions run and was merged normally. No workflow run/status was returned for the merge SHA itself, so CI for `953d62e...` is `unknown`.
- The quality-branch harness reporter fix (`e8be1f5...`) was made after the live reports. It fills missing manual-case `token_budget` fields from the exact attempt metadata without changing the saved reports or their results. No second 27-case live run was performed after this reporting-only change.

## Limits and remaining work

The empty-content diagnosis is now separated from malformed schema in provider diagnostics on main. The local Qwen3/custom-template candidate did not resolve thinking-only output; the 1024 budget helped one task but failed translation and approaches the timeout. Qwen2.5 was fast but failed translation language and produced repetitive, overlong Gateway answers. The application default remains `qwen2.5:0.5b`; no candidate/default/model was promoted.

The live strict suite still has 11 contract failures and four task-uncertain outputs. No human content review is claimed. The 60-second timeout behavior and possible server-side work after client timeout need further diagnosis under a bounded Gateway trial. Next work: compare supported configs/models on the same locked synthetic tasks, improve the normal answer path without turning failures into success, rerun the strict Gateway suite and submit the four successful open-ended outputs plus the failed task outputs for human review. Do not report overall product quality as passed.


## Follow-up harness reporting correction

The historical `live-gateway-bilingual-review-qwen3-r1.md` was copied unchanged from the run. Its heading incorrectly says Qwen 2.5 0.5B, while the paired JSON configuration records expected model `qwen3:4b` and the run used that Qwen3 digest. This was a hard-coded label defect in the review-table generator, not a change to the report or its generated answers. Commit `7cfc2a4` changes future review tables to use `configuration.expected_model` (or `unknown model`) and adds a regression. Focused harness tests on that exact commit: 11 passed, exit 0. The sandbox-only attempt ended with Windows basetemp access-denied teardown and exit 1; it was rerun with normal filesystem access and passed. The strict live generation report above remains the unchanged prior run on `e89e57467fde95ed11d077033ecfbc23a30b7ff3`; it was not rerun after this report-label-only fix.


## Independent main integration

The review-table reporting correction was tested in an isolated worktree based on main `953d62efa5bf874b9852f6a02fcb7844258ec317`, then merged through [PR #5](https://github.com/quocdoanhdang2-sketch/dusnx-platform/pull/5). The exact PR head `b9f81c0b5eda44c41bf51bb153bed1a2d9462b77` had focused harness **8 passed**, full Python **260 passed, 1 skipped**, and GitHub Actions run [41696532438](https://github.com/quocdoanhdang2-sketch/dusnx-platform/actions/runs/41696532438) success. Remote main is now `5dd1052d9052da4ffbd0418b629e238a957a61eb`. No workflow or status was returned for that merge SHA itself; that status is unknown. This integration only corrects future review-table model provenance and does not resolve or promote generation quality.


## Installed DUSNX VI candidate probe (direct Ollama)

A small same-prompt comparison also used the already installed `dusnx-vi-candidate:latest` (digest `bd9ebfc9d9af8ce3f53224b3480e957e8d39a530ec2fba19ce12a54df4a1fbe3`, Qwen2 family, 494.03M parameters, F16, template SHA-256 `eb4402837c7829a690fa845de4d7f3fd842c2adee476d5341da8a46ea9255175`) on Ollama `0.40.14`. It used two repetitions each of the same synthetic translation/entity and Vietnamese Gateway-benefit prompts, `num_predict=512`, temperature 0.1, `num_ctx=4096`, repeat penalty 1.25, and no `think` field. This was direct `/api/chat`, outside the application stack; it does not establish Gateway behavior.

- Saved-script run R2 completed four requests, exit 0, in 0.28?0.66 seconds after warm-up. Translation was English in 2/2 but changed the exact URL scheme from `https://` to `http://` in both outputs, so entity preservation failed. Gateway-benefit outputs were concise and finished with `stop`; one of two mixed Vietnamese with Chinese. No independent factual review was done.
- The earlier exploratory R1 run is also retained, not replaced: both translation outputs stayed Vietnamese; both Gateway-benefit responses were around 2,000 characters and ended at `length`/512 tokens. Its exact inline script was not saved, so its command source is recorded as unknown; the tool returned exit 0 and the report records all four trials.
- This small probe is insufficient to promote the candidate. The model/default remains unchanged. The candidate demonstrates observed task/entity/language failures, not a quality pass.


## Integrity errata (2026-11-04)

The manifest now records separate SHA-256 values over retained source bytes, packaged worktree bytes, and exact committed Git blob bytes. It records BOM and CRLF/LF counts for each representation. A fresh raw-byte audit found 17 exact source/package pairs, 3 verified UTF-16LE-to-UTF-8 PowerShell-log conversions, and 2 authored artifacts whose independent source bytes were not retained (marked `unverified`). All 22 Git blob OIDs matched and their bytes were LF-normalized relative to the Windows worktree; the prior 1/16/5 grouping was not reproduced. Historical report files and results remain unchanged. The prior PR merge fields conflicted; `main_merged` is corrected to true from the recorded merge SHA, while CI for that merge SHA remains unknown.
