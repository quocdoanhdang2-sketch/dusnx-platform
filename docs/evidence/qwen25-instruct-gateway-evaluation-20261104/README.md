# Qwen2.5 1.5B Gateway quality follow-up

Synthetic-only live evidence for the isolated candidate model. The strict bilingual gate failed; the candidate remains unpromoted. Reports retain every case, failed attempt, and retry. `report.json` distinguishes LLM output, application formatting, and template recall.

A real app routing bug was found in VARIANT_28: URL query punctuation first caused a memory clarification; after that fix, `scope=read` inside the URL disabled entity validation. The second fix keeps independent KEY=VALUE literals under validation and returns `provider_error` after bounded corrective attempts that still omit/mutate the literal. The model still failed the translation task.

See `manifest.json` for exact code identity, commands/exit codes, model digest, per-artifact source/package SHA-256, and limits.

## Integration status (observed 2026-11-04)

The independent memory-routing correction was tested against main and merged through PR #6 at `7fe5ff9322b69a123cc2f7d7c64367d3ae9152e1`. Its PR-head Actions run passed all four jobs; no workflow run or commit status was returned for the merge SHA itself. Quality changes are tracked separately in PR #7 and remain unmerged because strict live generation failed. CI for the quality PR head had not returned a run/status when this note was written.
