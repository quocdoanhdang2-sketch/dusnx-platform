# DUSN-X benchmark_v1 contract

Each JSONL line is one uniquely identified step. `sequence_id` groups steps, and
`global_user_id` must remain constant within that sequence. Steps start at 1 and
are continuous. `case_id` is unique across the file.

`known_feedback_value` at step **t** is information already observed before step
**t** starts—normally feedback produced after step **t-1**. It must never contain
feedback about the response being predicted at step **t**. Step 1 therefore uses
`0.0`.

Required fields are defined by `dusnx_core.benchmark.BenchmarkStep`: identifiers,
step, platform, content, known feedback, expected intent/agent/action, category,
difficulty, source, authorship flag, and notes. Unknown fields are rejected.

`rule_impact.rescued` and `rule_impact.harmed` compare the complete expected route
(intent, agent, and action), not intent alone. Confusion matrices describe intent;
per-class precision, recall, and F1 are reported separately for all three targets.
Each target reports both `macro_f1_all_classes` (missing expected classes count as
zero) and `macro_f1_present_classes`, plus an explicit `missing_expected_classes`
list. Research comparisons should predeclare which macro is primary.

Allowed source labels are `human_authored`, `ai_generated`, and `test_fixture`.
Set `generated_by_ai=true` for AI-generated or AI-rewritten text. Such rows cannot
use `source=human_authored`. The checked-in fixture is only for automated tests;
its scores are not benchmark or research results.
