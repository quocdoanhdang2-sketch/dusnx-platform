# Post-hoc completion budget reassessment

This is a new analysis artifact, not a replacement for the historical Qwen3 run. It recomputes only completion metadata for the saved 1024-token report using the corrected evaluator; it does not rerun generation, alter responses, or change the historical contract/language/task results.

The source report used a 1024 token provider budget, but its completion evaluations were built from raw API metadata before the harness added the `token_budget` field to the report case. The evaluator therefore defaulted to 512. For completed calls with `done_reason=stop`, token counts 549–1023 were incorrectly described as reaching/exceeding a 512 budget. The saved report's case metadata later showed 1024. The corrected evaluator reads the actual provider attempt `num_predict`; without it, it records the budget as unknown rather than assume 512. Reaching the configured budget now yields `uncertain` even with `done_reason=stop`.

Reassessment of 14 saved `llm_generation` cases preserved task and contract outcomes. It changed the completion rationale in eight completed responses from “at/above budget” to “no provider limit”; case `CASE_05_AUTO_VI` remains uncertain at the true 1024 limit with `done_reason=length`. Existing task review remains 11 uncertain and still requires human review. Historical report content and totals are unchanged.

- Historical run code: `3747cbdaf4af9d8ea0ba7920c18c8bebf118cbe4`
- Reassessment base code: `002f5a8959625b0012d8526eb6a241efd8b2e7c0`
- Dirty harness/test patch SHA-256: `1295909f82aad538af3066838840e83c24cbe6287adaae9570e81cd0b37350c0`
- Source report: `../qwen3-invalid-schema-followup-20261104/gateway-qwen3-num-predict-1024-final-report.json`
- Source report SHA-256: `ff1329444d3182e22a8441565b805ac16b1eefa2414d14997c5181653b03a825`
- Method: offline post-hoc recomputation with saved synthetic output; no model call or human semantic assessment.
