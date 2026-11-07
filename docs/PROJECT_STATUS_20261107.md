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
| Word add-in | Proposal/Apply guards verified on Word Desktop (WordApi 1.1/1.3). | `docs/evidence/word-addin-desktop-20261106`. |
| PowerPoint add-in | Edit-selected-text and generate-slides modes verified on PowerPoint Desktop 16.0.20527. | `docs/evidence/powerpoint-addin-generate-20261107`. |
| SFT v3 candidate | Evaluation complete with `promote=false` (n=6). The base `qwen2.5:1.5b-instruct` remains the runtime model. | Paired evaluation report; candidate `dusnx-vi-v3-20261107`. |
| Production restart | Completed on 2026-11-07 with explicit consent. Ports 8000/8080 now serve the merged code, adaptive profile, RAG, and drafting gate. | `/health` source hashes match the working tree; Gateway smoke on 2026-11-07. |

## Verification run (local, 2026-11-07)

| Harness | Result |
|---|---|
| `pytest python/tests` | 395 passed |
| `node --test` (Web, PowerPoint, Word) | 58 passed |
| Gateway history tests | 7/7 passed; Release build 0 warnings / 0 errors |
| PowerShell local-health tests | 6/6 passed; `start-local.ps1` syntax OK |
| `python -m compileall -q python` | OK |
| Live AI API on isolated port 8046 | auto profile low / 4 GB / 1.5B; email and message drafts completed |
| Production 8000/8080 after restart | source hashes match; `model_profile` tier low / 4 GB / 1.5B; RAG 161 documents / 1,415 chunks; Gateway proxy answered a cited docs question, a drafting request, and the runtime clock |

These are local harnesses and live local probes. They are not a GitHub Actions run and
not a Desktop Office re-verification.

## Known limits

- The 1.5B baseline still produces uneven prose. Drafting requests now complete instead of
  being refused, but the content may be generic or awkward; it is not final correspondence.
- The quality gate measures language, required literals, repetition, and drafting completion.
  It does not measure factual correctness.
- Auto selection installs nothing. If the preferred model for a tier is absent, `/health`
  reports `preferred_model_missing` with a pull hint and uses the largest installed Qwen2.5
  model that fits.
- Containers cannot see the host GPU; pass `DUSNX_MODEL_VRAM_GB` or set the profile explicitly.

## Still open

1. Promote a candidate only after the frozen evaluation gate passes; Holdout v3 stays closed
   until then. Explicit consent does not replace missing evaluation evidence.
3. Teams, Zalo OA, and vision/image editing remain separate integrations that need real
   credentials and platform verification. No fake capability is exposed.
4. Office production hardening: signed/central manifests, same-origin HTTPS with an internal CA,
   sensitive-data retention, tracked changes/tables for Word, and Undo/telemetry for PowerPoint.
