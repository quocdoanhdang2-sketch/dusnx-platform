# Provider diagnostics integration evidence

This package documents a synthetic regression run on the isolated integration branch, based on reviewed main `937dc3c80a97f1cb2e5539fcab6bc3f15322013d` with the dirty application/test patch identified below. The run predates this evidence and its eventual documentation commit. It does not claim the test ran on the documentation commit.

- Branch: `integrate/provider-diagnostics-43b811e`
- Code base SHA: `937dc3c80a97f1cb2e5539fcab6bc3f15322013d`
- Dirty code/test patch SHA-256 (from `git diff --binary`): `301ac9d63b1a59315979acb57713bd4aa779a5b74d6eba8a9ad99ad954d0d500`
- Runtime: Windows; Python `.venv` executable, Python 3.14.7; pytest from that environment.
- Model generation was not run in this regression suite. No model, checkpoint, database, raw conversation, or private runtime log is included.

## Runs

Full Python suite: 258 passed, 1 skipped, exit 0. Command: `.\.venv\Scripts\python.exe -m pytest -q --basetemp ..\test-output-provider-diagnostics-20261104\pytest-full-final`, working directory `python`. This includes malformed response handling, thinking-only content metadata, direct and urllib-wrapped timeout classification, synthetic secret redaction, and chat receipt replay provenance.

The first full-suite attempt exposed eight tuple-mock compatibility failures. The implementation was updated to read optional diagnostics with `getattr`. A subsequent review also covered urllib-wrapped socket timeouts; the final full suite above ran on the resulting patch. This evidence covers provider-response diagnostics, not semantic answer quality or model promotion.

## Diagnostic scope

The Ollama adapter records safe scalar metadata from the actual response: `done`, `done_reason`, `eval_count`, `prompt_eval_count`, content/thinking character counts, returned/configured model, configured token budget, timeout, latency, schema status, and stable error category. Raw content, thinking, prompts, URLs, exception strings, credentials, and headers are not returned as diagnostic fields. Chat receipt replay carries the original safe metadata under `original_provenance`; replay itself reports no new provider call.
