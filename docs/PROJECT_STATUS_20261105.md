# DUSN-X Project Status — 2026-11-05

This update supplements the historical status reports. It records the LLM v2 work completed on 2026-11-05 and separates verified local results from work that remains. Local Windows artifacts are not included in this repository.

## Status at a glance

| Area | Status |
|---|---|
| Core DUSN-X demo system | Previously verified in the project handoff reports; this update does not re-run those runtime checks. |
| LLM v2 human review and data lock | Completed locally. Train and validation were reviewed; the independent 15-completion test was authored and reviewed before predictions. The staging manifest is locked. |
| Candidate v2 SFT | Completed locally for 3 epochs using LoRA. The run used the pinned Qwen2.5-0.5B-Instruct revision, max length 640, BF16 on an RTX 3050 Laptop GPU. |
| Base-versus-adapter validation comparison | Completed on validation only. Teacher-forced completion loss and next-token accuracy favored the adapter on these 24 validation examples. This is not free-generation evaluation or a promotion decision. |
| SFT workflow code | Merged to `main` through PR #9, merge commit `dceb553c725688e657f6f94def507c5777a316c6`. The focused SFT suite passed: 53 tests. |
| Candidate promotion / public production | Not completed. Keep the current base as the default until the remaining evaluation gate passes. |

## LLM v2 evidence

- Locked partitions: 100 train records, 24 validation records, and 8 independent-test records with 15 assistant completions.
- Exact-tokenizer audit: pinned Qwen2.5-0.5B-Instruct revision `7ae557604adf67be50417f59c2c2f167def9a775`; max length 640; human review complete.
- Training run: `runtime/llm-v2-human-gate-20261104/full-sft-maxlen640-retry-20261105-161905`.
- Adapter: `adapter/adapter_model.safetensors`; SHA-256 recorded in local evaluation provenance as `bae3d5754cd329aa7c82f2d31da3621d8648ff10dcb639e8e31bf3def81715fd`.
- Validation source SHA-256: `60d7c4851df0b869b0f8867b044aaed6320a8645993ebff6f834c71de1aabb48`.

| Model | Validation completions | Target tokens | Loss | Next-token accuracy |
|---|---:|---:|---:|---:|
| Base | 24 | 406 | 2.3154 | 52.96% |
| Adapter | 24 | 406 | 1.5230 | 65.52% |
| Adapter minus base | — | — | -0.7925 | +12.56 percentage points |

The paired comparison used the same prompt, tokenizer revision, precision, and scoring method. It measures teacher-forced prediction of reviewed validation completions. It does not establish better free generation, independent-test performance, or statistical superiority.

The training manifest reports that multi-turn completion masking was not exercised by the train split (`multi_turn_completion_mask_verified=false`). The smoke run exercised masking with a synthetic multi-turn case; the training data itself remains single-turn.

## Remaining work before promoting candidate v2

1. Export the local adapter against the pinned base and produce the documented GGUF/export package with checksums.
2. Import the candidate into Ollama under a separate name; preserve the base model for rollback.
3. Run the frozen base-versus-candidate generation comparison through the Gateway. Use the independent human-reviewed test only for the final evaluation, without tuning on its results.
4. Have a human score the generation outputs against the predeclared gate in `docs/WEEK3_LLM_TRAINING.md`. Promote only if every required criterion passes; otherwise keep the base.
5. Keep the separate Holdout v3 closed until the candidate and evaluation protocol are frozen. Do not use Holdout v3 to tune prompts, rules, or model settings.

## Artifact location and release boundary

The SFT run, adapter, validation comparison, and provenance currently live under the user's Windows `runtime/llm-v2-human-gate-20261104` directory. They are not model binaries in GitHub and this report does not claim they are reproducible from repository contents alone. The repository contains the SFT workflow and its tests, not the trained weights.

## Scope not required to finish this local SFT milestone

Public production hosting, real-time web search, and Word/Zalo integrations remain separate roadmap work. The previous handoff and release reports remain the source for the status of the core Web, Router, memory, and PowerPoint demonstrations.
