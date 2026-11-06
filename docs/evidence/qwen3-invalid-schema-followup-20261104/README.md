# Qwen3 invalid-schema diagnostics and quality follow-up

This package contains synthetic prompts and outputs only. It is evidence from prior local runs; it is not evidence that the later documentation/evidence commit or any newer code SHA was tested. No DB, WAL, account credentials, model weights, or private runtime logs are included. Raw provider outputs and thinking are retained because the diagnostic specifically examines `message.content` versus `message.thinking`; all corresponding prompts/accounts were synthetic.

## Baseline and provenance

- Repository: `quocdoanhdang2-sketch/dusnx-platform`.
- Branch during runs: `fix/quality-context-evidence`.
- Report `code_sha` / HEAD at run start: `3747cbdaf4af9d8ea0ba7920c18c8bebf118cbe4`.
- `origin/main` observed after fetch: `937dc3c80a97f1cb2e5539fcab6bc3f15322013d`.
- Working tree was dirty with tracked quality/provider/harness edits at run time. The exact tracked patch hash at run start was not snapshotted (`unknown`). For comparison only, the tracked code/test diff SHA-256 at evidence packaging, before code commit `43b811e`, is `30582c9c5404655d273fa1653c2b27f24d062a99d438e049b710f9a11baa2bd5`; it must not be attributed to the earlier run.
- The final run report itself records `execution_status=completed`; the shell process exit code was not captured (`unknown`). Re-evaluating its recorded summary using the strict gate yields exit code `1` because `contract_failed=4` and `task_uncertain=11`.
- Run started at `2026-11-03T16:49:08.444929+00:00` and the final report/review files were written at `2026-11-04T00:07:50+07:00` (UTC file timestamp `2026-11-03T17:07:50Z`).
- Final code was later changed only to restore Vietnamese provider-error wording and associated assertion; those wording-only source changes were covered by focused and full Python regression runs, but were not loaded by the already-running final Ollama stack.

## Runtime and configuration

- Live pipeline: local .NET Gateway -> FastAPI -> configured router/checkpoint -> local Ollama native API. Synthetic DB/account/output directory was new for each run.
- Ollama: `0.40.14`. Model: `qwen3:4b`, digest `359d7dd4bcdab3d86b87d73ac27966f4dbb9f5efdfcc75d34a8764a09474fae7` (Q4_K_M, 4.0B). No default model was changed or promoted. `/api/show` capabilities observed: completion, tools, thinking; the capability response did not provide a supported thinking-option value.
- App comparison settings: `num_ctx=4096`, `num_predict=512` or `1024`, temperature `0.1`, repeat penalty `1.25`, repeat_last_n `64`; per-call Ollama timeout `60s`, total-generation timeout `85s`, Gateway timeout `90s`.
- Existing router checkpoint path: `training-results/colab-run-01/extracted/dusnx-router-full-01/router.pt`; SHA-256 `56f56e6d61afc264fb02d690d2872fb3ac5db9749a659c8493fd9d99eab7e7b1`. Checkpoint file is not copied.
- Python venv: `3.12.10`; pytest full run: `300 passed, 1 skipped`; focused provider/harness run: `63 passed`. Pre-commit full pytest command: `python\.venv\Scripts\python.exe -m pytest -q --basetemp runtime/quality-work-20261103/pytest-full-final-r3` (working directory `python/`); `300 passed, 1 skipped`. After commit `43b811e`, the same suite ran with basetemp `runtime/quality-work-20261103/pytest-committed-43b811e-r1`; `300 passed, 1 skipped` (successful completion, exit `0`).
- Gateway history regression executable: `dotnet run --project .\gateway-dotnet.tests\Dusnx.Gateway.Tests.csproj --no-restore`; `7/7` passed, exit `0`. The `dotnet test` invocation on this executable project emitted no test output and is not counted as a test result.

## Findings

### Direct Ollama native API

| Trial | HTTP | `done_reason` | eval tokens | content chars | thinking chars | elapsed ms |
| --- | ---: | --- | ---: | ---: | ---: | ---: |
| default_128 | 200 | length | 128 | 0 | 719 | 11077.33 |
| default_512 | 200 | stop | 367 | 175 | 1895 | 14191.46 |
| default_1024 | 200 | stop | 275 | 122 | 1327 | 10720.81 |
| no_think_512 | 200 | stop | 416 | 130 | 2043 | 16506.97 |

At `num_predict=128`, Ollama returned HTTP 200 and `done=true`, but `done_reason=length`, 128 eval tokens, empty `content`, and 719 `thinking` characters. At 512/1024 the same short synthetic task returned non-empty content and `done_reason=stop`. `/no_think` did not suppress thinking in this local model/runtime (2,043 thinking characters); it is not treated as a fix. These direct calls establish the response shape, not app quality.

### Live Gateway suite results

| Run | Cases | Contract | Successful real generations | Empty-content responses | Language | Task uncertainty | Completion | Strict gate |
| --- | ---: | ---: | ---: | ---: | --- | ---: | --- | --- |
| num_predict=512 | 27 | 17/27 | 5 | 9 | 5/5 matched | 5 | 3 failed / 0 uncertain | 1 (recomputed; process exit unknown) |
| num_predict=1024, pre-correction harness | 27 | 25/27 | 12 | 2 | 13/13 matched | 11 | 0 failed / 9 uncertain | 1 (recomputed; process exit unknown) |
| num_predict=1024, final harness | 27 | 23/27 | 11 | 3 | 11/11 matched | 11 | 0 failed / 1 uncertain | 1 (recomputed; process exit unknown) |

On the final 1024 run, 3 normal-generation cases returned `content_chars=0`, `thinking_chars` 4,235 / 4,774 / 4,770, `eval_count=1024`, and `done_reason=length` after 56.8 to 58.9s. A separate user-B request in `CASE_11_TWO_USERS_LANGUAGE_ISOLATION` timed out after about 62.1s with a 60s provider timeout. The other expected offline/missing-model failures are test controls, not normal generations. The final run therefore has 4 contract failures, 11 matched-language outputs out of 11 eligible generated outputs, 11 task reviews uncertain, and one completion uncertain. No factual/content human review is claimed.

Changing the budget from 512 to 1024 reduced empty-content failures across repeated runs, but the final 1024 run still had three empty-content responses and one timeout; a prior matched 1024 run had two contract failures while the final repeated run had four. Latency also rose. For the 14 Qwen-configured provider attempts longer than 1 second in each run, median/p90/max was 27.9/30.1/30.5s at 512, 32.8/57.8/59.3s in the first 1024 run, and 48.0/58.9/61.9s in the final 1024 run. These include correction attempts; the final run also includes the 62.1s timeout. Repeated-run differences are retained. Because 1024 approaches the 60s per-call timeout and did not pass strict quality, no product default was changed.

The corrected completion evaluator now treats clear dangling clauses/unclosed code as failures, `done_reason=length` without clear truncation as uncertain, and `done_reason=stop` as provider-completed even when the reported eval count meets/exceeds the configured budget. The historical pre-correction report remains unchanged; the final report uses the corrected evaluator.

## Commands and exit status

- Final live command (working directory `python/`): set `$env:DUSNX_OLLAMA_NUM_CTX='4096'`, `$env:DUSNX_OLLAMA_NUM_PREDICT='1024'`, `$env:DUSNX_OLLAMA_TIMEOUT='60'`, `$env:DUSNX_GENERATION_TOTAL_TIMEOUT='85'`, and `$env:DUSNX_GATEWAY_TIMEOUT='90'`, then run `python\.venv\Scripts\python.exe ..\scripts\verify_bilingual_generation.py --expected-model qwen3:4b --expected-model-digest 359d7dd4bcdab3d86b87d73ac27966f4dbb9f5efdfcc75d34a8764a09474fae7 --strict-language --strict-quality --output-dir ..\runtime\quality-work-20261103\qwen3-providerdiag-num1024-final-r1`. Exact shell process exit code: `unknown` (not captured); strict-gate result recomputes to `1`.
- `num_predict=512` and pre-correction `num_predict=1024` commands are recorded in their respective report JSON. Process exit codes were not captured (`unknown`); both strict-gate results recompute to `1`.
- Direct Ollama diagnostic command source was not preserved as a checked-in script (`unknown`); JSON records exact native endpoint, request payload, response body, response SHA-256, timeout, and per-trial measurements.
- Python tests: final focused `63 passed` and full `300 passed, 1 skipped`; both succeeded.
- Gateway history tests: `7/7` passed using the project executable; exit `0`.

## Artifacts and integrity

JSON files were copied byte-for-byte from the `runtime/quality-work-20261103/...` source directories. Markdown review tables were copied unchanged. Git attributes below enforce LF normalization for this folder; the table lists SHA-256 of the source/copy bytes and expected LF-normalized committed content. No runtime DB/WAL, authentication data, model file, or process log is included.

| Evidence file | Source | Source/copy SHA-256 | LF-normalized SHA-256 |
| --- | --- | --- | --- |
| `direct-ollama-native-diagnostics-r1.json` | `runtime/quality-work-20261103/ollama-response-diagnostics-r1/report.json` | `3036d2f179df2b863287e97306bbb6c995b4bed18face2a0b9d3fa5c0e9689d4` | `43d9ed217dc59ac8de1e78d98018fd38dbc28a8300d97e15cfc9a5a5003253d6` |
| `gateway-qwen3-num-predict-512-report.json` | `runtime/quality-work-20261103/qwen3-providerdiag-r1/report.json` | `159dc53c9f7383a5d9a7124d73cad942c6030dfa996535f748a60baa9bbfa06a` | `6f405bf84326e763d5f4898aa578b4990bc8295282449b9726edabf02c0694a4` |
| `gateway-qwen3-num-predict-512-review.md` | `runtime/quality-work-20261103/qwen3-providerdiag-r1/review_table.md` | `dba9fa3d38d616a94e57962911858a7a19b0007bf3b71b83d3c18b080a07cbde` | `f1a7b0a555488b05c337c1cbcf240ec406fe47237d5e07fdabf197ff5eeab99b` |
| `gateway-qwen3-num-predict-1024-precompletion-fix-report.json` | `runtime/quality-work-20261103/qwen3-providerdiag-num1024-r1/report.json` | `24cb0630f0004be1d2e3e74169d04ee3cee107cc8f9d081f6796a0fbb5458411` | `af67348c73677379b15ac16de9026dea59b3dea4307a1ff46ef04238b6512061` |
| `gateway-qwen3-num-predict-1024-precompletion-fix-review.md` | `runtime/quality-work-20261103/qwen3-providerdiag-num1024-r1/review_table.md` | `e847dc11a15ce9c5a3de050a993262a09d46901f15ce1da6567b5d220de7e7f1` | `120029d571c7ee9c74647faf1c967a88fd205097b3d5165bf21d562b5efe6d6f` |
| `gateway-qwen3-num-predict-1024-final-report.json` | `runtime/quality-work-20261103/qwen3-providerdiag-num1024-final-r1/report.json` | `fd755ca39e8f981459ecd9c1afcdc992a15e8ccfb2f5449e73f74ef705002964` | `ff1329444d3182e22a8441565b805ac16b1eefa2414d14997c5181653b03a825` |
| `gateway-qwen3-num-predict-1024-final-review.md` | `runtime/quality-work-20261103/qwen3-providerdiag-num1024-final-r1/review_table.md` | `191ab6aa8378ed64007036035ef77390fe690bed416fa429160fc80b03180dfd` | `65148cf8f9d519a646a7efc656ccfaaa169e604f485ba258fa84aad8a58d3e30` |
| `ollama-runtime-capabilities.json` | `Read-only local ollama --version and POST /api/show response extract` | `307150938688f1317fb7d286c3d0f1eb54331c06fe23f0588953f973193038f4` | `307150938688f1317fb7d286c3d0f1eb54331c06fe23f0588953f973193038f4` |
| `review_queue.md` | `Generated from the final report; reviewer and decision fields intentionally blank` | `5f5efcad3bf82d46619cf9478e27d6a6101ea64da840c3ed54ae0e25abc1ed52` | `5f5efcad3bf82d46619cf9478e27d6a6101ea64da840c3ed54ae0e25abc1ed52` |

`review_queue.md` has blank human decision fields for all uncertain tasks. `ollama-runtime-capabilities.json` is a small extract of the read-only local `/api/show` response and `ollama --version`; it does not contain model weights or private configuration.

## Secret and privacy review

All prompts, conversation histories, and generated outputs are synthetic. Files were scanned for bearer tokens, JWT-shaped strings, OpenAI-key-shaped strings, and email addresses; no matches were found. Password-related words occur only in synthetic explanatory/evaluation text. Only reports, review tables, this manifest, and a sanitized capability extract are included.
