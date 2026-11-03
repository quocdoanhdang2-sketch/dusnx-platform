# Verification evidence: 5bd3682

- Code checked: `5bd3682c22398d41d90451b99595558aad060e3b`.
- These files are evidence from a previous run. They are not results from a run on the documentation commit that adds this folder.
- `runtime/bilingual-generation-release-final/report.json` contains no harness report paths or command/exit-code fields. Command and exit code are recorded as `unknown`; no substitute results were created.
- Harness report copied: `runtime/backup-restore-final-pass/report.json` (timestamp recorded below); the chat provenance report is separately included. No other harness report is claimed as part of this run.
- Sanitization: removed opaque 32-character IDs and local ephemeral port values; secret-like fields are omitted or redacted. Source SHA-256 identifies the original artifact; copied SHA-256 identifies the sanitized copy.

## Artifacts

| File | Source | Artifact time (UTC) | Source modified (UTC) | Source SHA-256 | Copied SHA-256 | Command | Exit code | Status |
|---|---|---|---|---|---|---|---|---|
| `bilingual_generation_report.json` | `runtime/bilingual-generation-release-final/report.json` | 2026-11-03T06:12:41.424466+00:00 | 2026-11-03T06:13:33.147793+00:00 | `a3d44bcedd2d113b9bc9994f0685e839599c31565ae7ce58e42ab397fc99cb5e` | `30716eea67fcf8eccd4050311d6ad874cb45bfc86c2cc7dc55df9d20364af797` | unknown | unknown | copied_and_sanitized |
| `bilingual_review_table.md` | `runtime/bilingual-generation-release-final/review_table.md` | 2026-11-03T06:12:41.424466+00:00 | 2026-11-03T06:13:33.148301+00:00 | `f1c443dc9848c99d7543ace3d7410cfffbed11fff8665857e695dfd26b388af1` | `f1c443dc9848c99d7543ace3d7410cfffbed11fff8665857e695dfd26b388af1` | unknown | unknown | copied_and_sanitized |
| `chat_provenance_report.json` | `runtime/provenance-verify-run/report.json` | 2026-11-03T06:12:18.399450+00:00 | 2026-11-03T06:12:27.284060+00:00 | `06b8d44d2df1ca1af737f2c327bba5f6d998f67b9e6b01b67174779b8f217f22` | `db5c3c3c27cc9b78582daa287f93b2489aa1c3446fd74da5b9dc7d8020434cfe` | unknown | unknown | copied_and_sanitized |
| `backup_restore_harness_report.json` | `runtime/backup-restore-final-pass/report.json` | 2026-11-03T06:13:42.917680+00:00 | 2026-11-03T06:13:54.086406+00:00 | `b01454c0d474423d15b8e81445b72234d7b83d67e738365a282685a1db06ec9c` | `c7a045cbad7d0babafcf85b170a907ed9a536c54d566816cd8453d1a0e031456` | unknown | unknown | copied_and_sanitized |

## Missing artifacts

- Harness report paths were not listed in the bilingual report; no additional report could be identified from that report. Additional harness outputs not proven to belong to this run are omitted.
