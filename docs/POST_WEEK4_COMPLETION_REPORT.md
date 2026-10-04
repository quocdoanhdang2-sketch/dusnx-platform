# Post-Week 4 completion report

Start HEAD: `7a15ee13217f2239d4bf9780bded6a8163831505`. Final HEAD and CI URL are reported after push.

Implemented: safe opt-in Inspector, VI/EN/auto API policy and preference memory, Web selector,
repeatable demo script, authenticated PowerPoint proposal/apply task pane, production configuration
guards, bounded local security/performance probes, and isolated SFT v2 draft data. Root causes fixed
during runtime: CSP initially blocked legacy inline Web handlers; oversized proxy bodies surfaced as
503 instead of 413; Chromium verifier used string eval disallowed by CSP.

Runtime evidence: trained router checkpoint hash `56f56e6d61afc264fb02d690d2872fb3ac5db9749a659c8493fd9d99eab7e7b1`,
base `qwen2.5:0.5b`, real Chromium passed eight checks, HTTP demo completed save/propose/confirm/new
session recall, English generation reported `detected=en/response=en`, and Inspector exposed filtered
metadata without auth token. Local health load 30 sequential requests: p50 0.86 ms, p95 1.48 ms,
0% errors, 241.59 req/s; this is not production capacity. Unsupported content type returned 415 and
oversized content returned 413.

LLM v2 data: train 100/100 sequences/pairs, validation 24/24, test draft 16/16, all AI-generated
`needs_human_review`. Exact prompt duplicate is zero, but max cross-split near similarity is 0.9689
and many within-split templates exceed 0.98. The quality gate therefore remains closed:
`training_allowed=false`; candidate `dusnx-vi-en-candidate-v2` was not trained/evaluated/promoted.

Holdout v3 manifest hash remains `094268aaf47fa5328786846aff46ebe2f271fd05e2633e681fee472adc8e71bd` and status
`labels_locked_not_independently_reviewed`. No model, baseline, rule or scorer was run on it.
PowerPoint XML/task pane/mock tests ran; PowerPoint Desktop was not clicked by the agent.

Checks before handoff: Python 196 passed; Web 11 passed; PowerPoint 2 passed; Gateway 7/7;
PowerShell health 6/6; .NET Release 0 warnings/errors; XML well-formed; compileall passed.

## USER ACTION REQUIRED

1. Data reviewer: open `docs/evidence/llm-sft-v2/data-quality-review.md`, rewrite/review diverse
   multi-turn examples, rerun audit at 0.82, lock test before any prediction. Success means an
   independent receipt and manifest permit training; only then prepare/run Colab candidate v2.
2. Holdout reviewers: follow `docs/HOLDOUT_V3_REVIEW_GUIDE.md`. Success means independent review,
   adjudication and valid receipt/lock; only then run the one-shot protocol.
3. PowerPoint Desktop owner: follow `docs/POWERPOINT_ADDIN_RUNBOOK.md` to trust localhost HTTPS and
   sideload the manifest. Success means proposal remains separate until Apply changes selected slide.
4. Deployment owner: supply domain/TLS/secret-store values from `docs/DEPLOYMENT_GUIDE.md`; no paid
   service or domain was created automatically.
