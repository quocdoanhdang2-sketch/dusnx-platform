# Provider-error language scoring correction

This independent harness-only change was evaluated from latest main `4d75b0f606476467fd5db385f7e52d789c94e1c4`, with the exact dirty source patch identified in `manifest.json`.

The bilingual report previously ran its language heuristic on localized `provider_error` text. It could therefore report a language match or mismatch even though no model answer existed. The harness now marks those outputs `not_applicable`, excludes them from the language denominator, and aggregates user-isolation results using only successful provider outputs. This changes reporting only; it does not modify application or model behavior.

Validation on this exact main-based working tree:

- `python/.venv/Scripts/python.exe -m pytest python/tests/test_harness_contracts.py -q`: 7 passed, exit 0.
- `python/.venv/Scripts/python.exe -m pytest python/tests -q`: 256 passed, exit 0.
- `git diff --check`: exit 0.

See `manifest.json` for source and evidence hashes, timestamps, commands, tool versions, and dirty patch identity.
