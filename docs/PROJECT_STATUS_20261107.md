# DUSN-X Project Status — 2026-11-07

This update records the retrieval, model-selection, and drafting-gate work completed on
2026-11-07. It distinguishes verified local runtime evidence from work that is still open.
Local `runtime/` artifacts stay outside the repository.

## Status at a glance

| Area | Status | Evidence |
|---|---|---|
| Grounded retrieval (RAG) | Integrated. Answers cite only the passages they use; SQLite FTS5 index has 161 documents / 1,415 chunks. | Live `/v1/chat` probes on 2026-11-07; `python/tests/test_rag.py`. |
| Retrieval isolation | Translation and rewriting requests skip retrieval, so repository text is never quoted as the answer. | `docs/PROJECT_STATUS...` probes; `test_response_quality.py`, `test_rag.py`. |
| Per-machine model profile | Implemented. VRAM tiers pick an installed Qwen2.5 model: low < 6 GB, mid 6–12 GB, high ≥ 12 GB. Explicit `DUSNX_OLLAMA_MODEL` or `DUSNX_MODEL_PROFILE` overrides auto. | Live `/health.model_profile` on a 4 GB machine: `tier=low`, `vram_source=nvidia-smi`, `qwen2.5:1.5b-instruct`. |
| Direct drafting requests | Quality gate now detects a refused or deferred email/message draft and sends one bounded corrective attempt. `drafting_status` is recorded per attempt. | `assess_drafting_completion`, `test_response_quality.py`; live probe `runtime/email-draft-probe-20261107.txt`. |
| Vietnamese observance dates | Known dates (20/11, 2/9, 30/4, …) are answered from a checked local calendar without a provider call; follow-ups, bare dates, and other-year questions get the recurring observance plus an explicit "not verified for that year" caveat instead of invented details. | `python/apps/ai_api/observances.py`, `python/tests/test_observances.py`; isolated live probe on 8046/8180. |
| Runtime model identity | "DUSN-X dùng model nào?" is answered from runtime state (`model_profile.resolve_model_profile()`), not retrieval, so documentation about the 0.5B candidate cannot be reported as the running model. | `answer_runtime_model_question`, live probe on 8180: `qwen2.5:1.5b-instruct`, profile `low`. |
| Language control | Deterministic language policy plus one bounded corrective retry; a divergent/mixed draft gets a dedicated translation pass. Sanitizer strips leaked prompt headers and correction meta-commentary. | `language.py`, `provider.py`; live probes: en→en, vi→vi, English question with Vietnamese preference → Vietnamese answer, no meta text. |
| External AI provider | OpenAI-compatible client supports OpenAI, Gemini compatibility endpoint, LM Studio, and vLLM. Fallback to local Ollama only when the external provider is configured but unreachable; a missing key surfaces as a configuration error. | `provider.py`, `.env.example`; unit suites. **Live since 2026-11-07** with an operator-supplied Gemini key: provider `openai`, model `gemini-3.1-flash-lite` (3.8-flash and 2.5-flash are retired or slower on this key), fallback `ollama`. Live probes: "Thủ đô của Úc" → `Canberra` and a Word-marked rewrite both answered by Gemini in ~1 s through the Gateway. `DUSNX_OPENAI_TIMEOUT=150` and `DUSNX_GATEWAY_TIMEOUT=200` stay as headroom. |
| Simple arithmetic | Plain expressions are evaluated deterministically (AST-based, no `eval`); observed `2+2 -> 5` from the local model is no longer possible. Non-arithmetic questions are not hijacked. | `python/apps/ai_api/arithmetic.py`, `python/tests/test_arithmetic.py`; live probe on 8180: `2+2 = 4`, provider not called. |
| Chat sessions | Sessions are created lazily on the first message; empty sessions are hidden. The first message titles the session on every reply path, including deterministic fast paths, and the header updates with the sidebar. | `web-ui/app.js`, `main.py`; live 8180 probe: one row per session, title `20/11 là ngày gì?`. |
| Chat rendering | Assistant replies render headings, lists, emphasis, inline code, fenced code and http(s) links through DOM nodes only; raw HTML and other URL schemes stay literal text. Each reply has a copy action. | `renderMarkdown`, `copyMessageText`; `web-ui/app.test.js` XSS and markdown tests. Not yet re-checked in a visible browser this round. |
| Long-term memory | Repeating the same explicit "remember" instruction reuses the existing row instead of creating a duplicate; edits still go through versioned supersede. The chat shows which saved memories were used. | `main.py` explicit memory flow, `buildUsedMemoryCard`; `test_memory_quality.py`, `web-ui/app.test.js`. |
| Office request routing | Word/PowerPoint messages carry a marker and are routed straight to the provider: calendar, calculator, runtime identity, RAG quotations, clarification guards and memory/decision flows cannot answer them, so the add-in provenance check always receives a real LLM result. | `_is_office_request`, `force_provider`; `python/tests/test_office_routing.py`. |
| Word add-in | Proposal/Apply guards verified on Word Desktop (WordApi 1.1/1.3). Apply now supports Replace selection or Insert new paragraph after selection; both re-check the selection before writing. | `docs/evidence/word-addin-desktop-20261106`; insert-after covered by the Node harness, not yet re-verified on Desktop. |
| PowerPoint add-in | Edit-selected-text and generate-slides modes verified on PowerPoint Desktop 16.0.20527. Generation can insert after the currently selected slide (or after the last slide) and refuses if the reviewed target slide was deleted. | `docs/evidence/powerpoint-addin-generate-20261107`; target selection/deletion covered by the Node harness, not yet re-verified on Desktop. |
| SFT v3 candidate | Evaluation complete with `promote=false` (n=6). The base `qwen2.5:1.5b-instruct` remains the runtime model. | Paired evaluation report; candidate `dusnx-vi-v3-20261107`. |
| Production restart | Completed on 2026-11-07 with explicit consent, twice: first for `25034d5`, then for `7792ffc` which adds safe Markdown rendering, memory recall/dedup, Office request routing, Word insert-after and PowerPoint selected-slide insertion. | `/health` source hashes match the working tree at `7792ffc`; live chat probes through Gateway on 2026-11-07. |

## Verification run (local, 2026-11-07)

| Harness | Result |
|---|---|
| `pytest python/tests` | 425 passed, 1 skipped |
| `node --test` (Web, PowerPoint, Word) | 66 passed |
| Gateway history tests | 7/7 passed; Release build 0 warnings / 0 errors |
| PowerShell local-health tests | 6/6 passed; `start-local.ps1` syntax OK |
| `python -m compileall -q python` | OK |
| Live AI API on isolated port 8046 | auto profile low / 4 GB / 1.5B; observance, year caveat, runtime model identity, and vi/en language probes answered; `provider_called=false` on fast paths |
| Isolated Web UI on 8180 | Lazy session creation, empty-state row, one titled session per conversation after refresh, header/sidebar title agreement, compact router label, runtime-identity chip. Structural inspection only — the in-app browser had no visible surface, so no screenshot was taken. |
| Upgrade round on branch `fix/quality-context-evidence` | Python 425/1 skipped, Node 66/66. Office request routing, Word insert-after, PowerPoint target selection, Markdown rendering and memory dedup are covered by unit/Node harnesses. No Desktop Office re-verification and no visible-browser run this round. |
| Production 8000/8080 after restart to `7792ffc` | `/v1/health` source hashes match the working tree (`main.py` `0e7d1b49…`); `provider_ok=true`, model `qwen2.5:1.5b-instruct`, tier `low`. Live probes through Gateway: `2 + 2` answered `4` with `provider_called=false`; repeated explicit remember kept one memory row; a Word-marked request returned `response_source=llm` with `provider_called=true`; a RAG question returned `rag_extract` with cited sources; served Web UI ships `app.js?v=20261107h`. |

These are local harnesses and live local probes. They are not a GitHub Actions run and
not a Desktop Office re-verification.

## Known limits

- The 1.5B baseline still produces uneven prose. Drafting requests now complete instead of
  being refused, but the content may be generic or awkward; it is not final correspondence.
- The quality gate measures language, required literals, repetition, and drafting completion.
  It does not measure factual correctness. The checked paths (observance calendar, runtime
  identity, simple arithmetic) are exact; outside them the small model can still state a wrong
  fact. ChatGPT/Gemini-level breadth needs a hosted model: set `DUSNX_PROVIDER=openai` plus
  `DUSNX_OPENAI_BASE_URL`, `DUSNX_OPENAI_MODEL`, and `DUSNX_OPENAI_API_KEY` (Gemini uses its
  OpenAI-compatibility endpoint). No key is bundled. The native launcher reads these from the
  launching shell only, so use `$env:NAME = "..."` before `start-local.ps1` or `setx NAME "..."`
  for a persistent user-level value; `.env` is consumed by Docker Compose, not by the script.
- Auto selection installs nothing. If the preferred model for a tier is absent, `/health`
  reports `preferred_model_missing` with a pull hint and uses the largest installed Qwen2.5
  model that fits.
- Containers cannot see the host GPU; pass `DUSNX_MODEL_VRAM_GB` or set the profile explicitly.

## Still open

1. Optional tuning now that Gemini is live: the runtime model is `gemini-3.1-flash-lite`
   (~1 s per answer on 2026-11-07 probes). If a heavier model is ever wanted, set
   `DUSNX_OPENAI_MODEL` (e.g. `gemini-3.8-flash`) and restart the AI API; expect free-tier
   queueing to make latency jump around.
2. Promote a candidate only after the frozen evaluation gate passes; Holdout v3 stays closed
   until then. Explicit consent does not replace missing evaluation evidence.
3. Teams, Zalo OA, and vision/image editing remain separate integrations that need real
   credentials and platform verification. No fake capability is exposed.
4. Office production hardening: signed/central manifests, same-origin HTTPS with an internal CA,
   sensitive-data retention, tracked changes/tables for Word, and Undo/telemetry for PowerPoint.