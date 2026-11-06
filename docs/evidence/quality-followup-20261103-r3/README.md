# DUSN-X quality follow-up evidence — 2026-11-03

This evidence records live synthetic Gateway → FastAPI → Ollama runs and Python regression tests performed on the dirty working tree based at `a2184b4530810e640c16e00b8d7ef89866f1372e`. The exact tracked-tree patch SHA-256 is in `manifest.json`. These results do not describe the later evidence/documentation commit.

## Results

| Run | Result | Strict exit |
| --- | --- | ---: |
| Qwen3 4B, final evaluator, 27 cases | Contract 16/27; 4/4 generated outputs matched expected language; 4 task reviews uncertain; 2 completion failures | 1 |
| Existing candidate, same 27 cases/settings | Contract 22/27; 10/10 generated outputs matched expected language; 9 task reviews uncertain; 3 quality flags | 1 |
| Qwen3 4B chat provenance | Model digest verified; provider contract failed; language/completion not applicable; task unreviewed | 1 |
| Existing candidate chat provenance | Transport passed; application quality rejected after 2 provider calls; language/completion not applicable; task unreviewed | 1 |
| Focused Python regressions | 54 passed | 0 |
| Full Python suite | 298 passed | 0 |

The Qwen3 runs are kept separately: `r1` predates the evaluator correction; `r2` includes general provider-error exclusion but predates the same correction in manually built language-isolation cases; `r3` is the final evaluator run. Do not treat `r1` or `r2` language counts as final.

Candidate output quality is still not accepted. The strict run has task uncertainties and provider/application failures. The ticket is intentionally open; no independent human review is claimed. No candidate was promoted and the default model was not changed.

## Model/configuration comparison

Both live runs used the same 27 locked cases, `num_ctx=4096`, `num_predict=512`, temperature `0.1`, repeat penalty `1.25`, and repeat-last-N `64` on an RTX 3050 Laptop GPU with 4 GiB VRAM. Qwen3 4B is a 2.497 GB Q4_K_M model; the existing candidate is a 994 MB F16 model. Across the 12 case requests that called a provider, the report's per-request `provider_elapsed_ms` had median/p90 of 27.36/30.06 seconds for Qwen3 and 4.05/7.94 seconds for the candidate. Successful requests alone had medians of 23.50 and 3.21 seconds, respectively. These are harness request timings, not a controlled throughput benchmark. A live GPU snapshot during Qwen3 execution read 2319 MiB used of 4096 MiB; comparable candidate peak VRAM was not captured, so no candidate VRAM claim is made.

The existing candidate completed more contract cases and was faster under these settings, but still had five contract failures, three quality flags, nine task uncertainties, and unreviewed factual risk. This comparison does not justify promotion.

See `manifest.json` for exact commands, environment, exit codes, timestamps, source and copied artifact hashes, model digests, and dirty-tree identity. Reports contain synthetic prompts, histories, and responses only; no credentials, databases, model files, or personal logs are included.
