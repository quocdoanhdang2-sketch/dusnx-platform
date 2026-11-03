# Verification evidence manifest ? final working tree (2026-11-03)

## Code identity and baseline

- Repository: `quocdoanhdang2-sketch/dusnx-platform`; branch: `fix/quality-context-evidence`.
- Base code SHA: `a5c9fa5be6fe7c0975f65ceef3129921a1b61556` (full SHA).
- Final source tree used for full pytest and strict bilingual r9: base SHA plus dirty patch SHA-256 `c691f0582ff21f4dd9efd3abbee55ef0774288bd77a090bca117c065995cbd9d`. Hash covers tracked source/doc changes and the new response-quality regression file. No source edits followed r9/full-suite runs.
- This records local runs on the patched working tree; it is not evidence that a later docs/evidence commit or remote commit was run.
- `origin/main` fetched before integration/push: `a5c9fa5be6fe7c0975f65ceef3129921a1b61556`. Content quality gates failed, so main was not updated.
- Initial checkout was clean on main; stash `local-wip-powerpoint-and-scripts` was left untouched. No reset/clean/stash operation, force push, protected-data access or public deployment.
- Final `git diff --check`: exit 0.
- Tests/harnesses use synthetic accounts, fresh databases and new output paths. Secret/password/token scan found no credentials in packaged artifacts. No DB, checkpoint file, weights or personal data are included.

## Environment and model

- Windows 11 build `10.0.26300`; Python `3.12.10`; pytest `9.1.1`; Node `v24.20.0`; .NET SDK `8.0.427`; Ollama `0.40.14`; Chrome executable `C:\Program Files\Google\Chrome\Application\chrome.exe`.
- Expected/configured live model: Ollama `qwen2.5:0.5b`, full digest `a8b0c51577010a279d933d14c2c8aab4b268079d44c5c8830c0a93900f1827c67`. Default model was not changed.
- Runtime checkpoint SHA-256 `56f56e6d61afc264fb02d690d2872fb3ac5db9749a659c8493fd9d99eab7e7b1`; checkpoint itself is not copied. Token budget: 512. Raw capture enabled only on synthetic harness traffic.

## Findings: observed before and after

- Existing CASE_05 evidence in `../verification-5bd3682/` showed Han text `??` in Vietnamese prose accepted as matched. Production language assessment now checks actual prose script independently from response-language metadata; code/URL and quoted-source exemptions have regression tests. Strict r9 contains one mixed-script case and does not silently pass it.
- Existing CASE_07 passed because the exact required entity occurred in echoed prompt text. Entity validation now removes prompt echoes and parses identifiers/values/URLs separately from task completion. Final r9 still correctly fails CASE_07: answer mentions `DUSNX_PORT=8088` but does not produce the requested configuration line.
- Existing CASE_09 answered a microservices follow-up with unrelated DUSN-X content. Current harness/app detects a short follow-up after multiple user-named topics and asks which topic; r9 records CASE_09 as an application clarification with no provider call. Topic-shift history starts at the switch point, and prior assistant content is marked unverified/excluded unless explicitly referenced.
- Provenance now separates transport, language and task scope. Final provenance status is `unverified`/exit 1 after real Ollama returned English for a Vietnamese generation request; after a bounded second call the API returned `provider_error`, `quality_status=failed`, rather than storing it as a successful assistant response.
- Provider metadata includes raw/sanitized hashes and text only in synthetic capture, done_reason, token budget, sanitizer changes, provider call count and attempt-level quality. One corrective call maximum; empty output and unrecovered language/entity/repetition failures do not become successful assistant messages.
- Re-running provenance with a new output initially hit a fixed-directory collision; the harness now creates a stack directory scoped by output filename. The final full suite includes its uniqueness regression, and provenance-r8 completed the isolated live stack.

## Verification results and blockers

- Full Python suite: exit 0, 273 passed.
- Node Web/auth/PowerPoint: exit 0, 26 passed. .NET Release Gateway build: exit 0, zero warnings/errors. Gateway history console tests: exit 0, 7/7. PowerShell local health: exit 0, 6/6.
- Real Chrome/Gateway/FastAPI/Ollama browser: exit 0, 8/8 checks, including a live Vietnamese generation. Auth: 5/5. History: 6/6, 205 messages ordered. Memory reliability: 10/10. Week 4 runtime: 19/19.
- SQLite synthetic backup/restore: exit 0, 205/205 messages across three pages; backup integrity/auth/retry passed. Protected-data level skipped because the explicitly supplied nonexistent protected path was absent; no protected DB opened.
- Strict bilingual r9 (`--strict-language --strict-quality`): exit 1. 18 cases; contract pass 14 / fail 4; real LLM generations 6; template recall 1; expected provider failures 2; 11 eligible language cases (10 matched, 0 divergent, 0 uncertain, 1 mixed); task_failed 3; task_uncertain 5; quality_flagged_cases 1; completion failures/uncertainties 0.
- r9 concrete failures: CASE_07 did not emit a `.env` config line; VARIANT_14 and VARIANT_15 changed or failed required config values; VARIANT_16 had mixed-script output and was returned as provider_error after retry. Five open-ended cases remain task-uncertain; uncertainty is not counted as pass.
- Provenance r8: exit 1, `unverified`; the actual generation request expected Vietnamese but received English. Two provider calls; final source `provider_error`, `quality_status=failed`.
- These failures and uncertainties block main integration. No protected branch bypass, force push, or deployment.

## Commands and exit codes

Working directory: `D:\Projects\dusnx-platform`. Harness outputs were created under `runtime/verification-final-20261103/` in unique directories.

| Suite/artifact | Command | Exit |
|---|---|---:|
| `bilingual-generation-report.json` | `python/.venv/Scripts/python.exe scripts/verify_bilingual_generation.py --output-dir runtime/verification-final-20261103/bilingual-r9 --strict-language --strict-quality` | 1 |
| `bilingual-review-table.md` | `same strict bilingual run; review column not auto-filled` | 1 |
| `chat-provenance-report.json` | `python/.venv/Scripts/python.exe scripts/verify_chat_provenance.py --spawn-stack --output runtime/verification-final-20261103/provenance-r8.json` | 1 |
| `web-auth-report.json` | `python/.venv/Scripts/python.exe scripts/verify_web_auth.py --output-dir runtime/verification-final-20261103/auth-r8 --chromium Chrome` | 0 |
| `chat-history-report.json` | `python/.venv/Scripts/python.exe scripts/verify_chat_history.py --output-dir runtime/verification-final-20261103/history-r8 --chromium Chrome` | 0 |
| `memory-reliability-report.json` | `python/.venv/Scripts/python.exe scripts/verify_memory_reliability.py --output-dir runtime/verification-final-20261103/memory-r8 --chromium Chrome` | 0 |
| `week4-runtime-report.json` | `python/.venv/Scripts/python.exe scripts/verify_week4_runtime.py --data-dir runtime/verification-final-20261103/runtime-data-r8 --output-dir runtime/verification-final-20261103/runtime-r8` | 0 |
| `web-browser-report.json` | `python/.venv/Scripts/python.exe scripts/verify_week4_web.py --output-dir runtime/verification-final-20261103/browser-r8 --chromium Chrome` | 0 |
| `sqlite-backup-restore-report.json` | `python/.venv/Scripts/python.exe scripts/verify_sqlite_backup_restore.py --output-dir runtime/verification-final-20261103/sqlite-r8 --protected-dir runtime/verification-final-20261103/no-protected-data-r8` | 0 |
| Full Python | `python/.venv/Scripts/python.exe -m pytest python/tests -p no:cacheprovider --basetemp D:/Projects/dusnx-platform/.test-runs-final-code-r4-20261103` | 0 |
| Node | `node --test web-ui/app.test.js web-ui/auth.test.js powerpoint-addin/taskpane.test.js` | 0 |
| .NET build | `dotnet build gateway-dotnet/Dusnx.Gateway.csproj -c Release` | 0 |
| Gateway tests | `dotnet run --project gateway-dotnet.tests/Dusnx.Gateway.Tests.csproj -c Release` | 0 |
| PowerShell health | `./scripts/tests/local-health.tests.ps1` | 0 |

## Artifact inventory

Source mtime is filesystem mtime in UTC. Source and copied-artifact SHA-256 values are listed separately. Runtime JSON has only the local checkpoint path redacted; SQLite JSON has only the local nonexistent protected-path string redacted. Other files were copied byte-for-byte after credential-pattern scan. No listed artifact is missing.

| Evidence file | Source | Source mtime (UTC) | Source SHA-256 | Evidence SHA-256 |
|---|---|---|---|---|
| `bilingual-generation-report.json` | `runtime/verification-final-20261103/bilingual-r9/report.json` | 2026-11-03T11:47:24.460001+00:00 | `854d05bc8b17127ff60384ea630d72ea10b6b55882176c3ffd49253bb382442b` | `854d05bc8b17127ff60384ea630d72ea10b6b55882176c3ffd49253bb382442b` |
| `bilingual-review-table.md` | `runtime/verification-final-20261103/bilingual-r9/review_table.md` | 2026-11-03T11:47:24.461001+00:00 | `d37bf4ff15d30164a3939102bbfd08aa088b6106c7bdcf7f4724c2b8ebb82c94` | `d37bf4ff15d30164a3939102bbfd08aa088b6106c7bdcf7f4724c2b8ebb82c94` |
| `chat-provenance-report.json` | `runtime/verification-final-20261103/provenance-r8.json` | 2026-11-03T11:41:40.854200+00:00 | `715c5674e32d912b4358ad706c170a7e952ad1a21e83dbd0010e763f3455aca9` | `715c5674e32d912b4358ad706c170a7e952ad1a21e83dbd0010e763f3455aca9` |
| `web-auth-report.json` | `runtime/verification-final-20261103/auth-r8/report.json` | 2026-11-03T11:43:35.179379+00:00 | `c539d1da5327a871690929327f6f6b16a1a17e32c5f78fa0f2b123d43e3c0e14` | `c539d1da5327a871690929327f6f6b16a1a17e32c5f78fa0f2b123d43e3c0e14` |
| `chat-history-report.json` | `runtime/verification-final-20261103/history-r8/report.json` | 2026-11-03T11:43:34.199636+00:00 | `2239d5a2713647b7c496007ee400e2f0074939f906d154e68176b69a3aee8091` | `2239d5a2713647b7c496007ee400e2f0074939f906d154e68176b69a3aee8091` |
| `memory-reliability-report.json` | `runtime/verification-final-20261103/memory-r8/report.json` | 2026-11-03T11:44:04.302454+00:00 | `fdd55d5a109cd4f875d203516790e0e5ddefa08905483085bbaee287cb3ea42e` | `fdd55d5a109cd4f875d203516790e0e5ddefa08905483085bbaee287cb3ea42e` |
| `week4-runtime-report.json` | `runtime/verification-final-20261103/runtime-r8/runtime.json` | 2026-11-03T11:44:22.679445+00:00 | `d34c000e551c6bddc7a0c68c990f1897facdfd795d938f317d1a91ea07de161f` | `8151553e89b31b820a594c1a3aeb966713fa87cc834127de4ac4a47a65fff8cd` |
| `web-browser-report.json` | `runtime/verification-final-20261103/browser-r8/browser.json` | 2026-11-03T11:40:40.610695+00:00 | `8c5b3b5d83f99f133018ff0d17391b7a8a41ca9b5bc32ba8992fdf48a1f7e7a8` | `8c5b3b5d83f99f133018ff0d17391b7a8a41ca9b5bc32ba8992fdf48a1f7e7a8` |
| `sqlite-backup-restore-report.json` | `runtime/verification-final-20261103/sqlite-r8/report.json` | 2026-11-03T11:43:59.114113+00:00 | `1851820aecaa8dc102d0a4ffa2213c2ab55a17552863a3a830ee656255b32f38` | `88fd1ffc97dd610e49284e459aa17b7456169efadd29704dbcf833e9ecd42e1b` |
| `pytest-full.log` | `full-pytest-final-code-r4-20261103.log` | 2026-11-03T11:42:55.607557+00:00 | `02f1ff9bf32f4c8aa4e1d00e96e5148d9fb2d435daaf782330c663669adb4a79` | `02f1ff9bf32f4c8aa4e1d00e96e5148d9fb2d435daaf782330c663669adb4a79` |
| `node-tests.log` | `runtime/verification-final-20261103/recorded/node-tests.log` | 2026-11-03T11:34:27.221323+00:00 | `679a7411ac55fd261c917f1937bcb77d8192cd26a9c0fbe457d8fa49082dcb84` | `679a7411ac55fd261c917f1937bcb77d8192cd26a9c0fbe457d8fa49082dcb84` |
| `dotnet-release-build.log` | `runtime/verification-final-20261103/recorded/dotnet-build.log` | 2026-11-03T11:34:28.260811+00:00 | `6bcaade8eee9955f15ef98d8168f46649e4ec7ed03f105114a4f2e30744bd765` | `6bcaade8eee9955f15ef98d8168f46649e4ec7ed03f105114a4f2e30744bd765` |
| `dotnet-gateway-tests.log` | `runtime/verification-final-20261103/recorded/dotnet-gateway-tests.log` | 2026-11-03T11:34:29.922585+00:00 | `583176b23804d406b15145365f9f9b59590fa9ec2817cbe54bbee4c991883909` | `583176b23804d406b15145365f9f9b59590fa9ec2817cbe54bbee4c991883909` |
| `powershell-local-health.log` | `runtime/verification-final-20261103/recorded/local-health-tests.log` | 2026-11-03T11:34:32.122065+00:00 | `258a6bf0fd2ab77d2c100a50dcf3c2ce26b2f3f3b6d69bc4864d8cec0443cc06` | `258a6bf0fd2ab77d2c100a50dcf3c2ce26b2f3f3b6d69bc4864d8cec0443cc06` |

### Markdown line endings

`bilingual-review-table.md` is a byte-for-byte copy of the generated source; source and evidence hashes are shown above. The source uses CRLF and Git may normalize its committed blob to LF. The staged Git blob SHA-1 is `e6403bd651680139d13c6fee6c4ed1d5882030da`; the evidence SHA-256 above identifies the original generated bytes. The review cells remain blank and labelled `needs_human_review`; no independent human review is claimed.

### Assessment limits

Language and task assessments are heuristics. Generic open-ended task correctness remains uncertain without rubric/human review and causes strict-quality failure. Template recall, application clarification, expected provider failures and real LLM generation are separate case types.
