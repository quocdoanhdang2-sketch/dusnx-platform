# Qwen3 think flag probe

This is a new, sanitized evidence artifact from one direct local Ollama request on `fix/quality-context-evidence`. It does not overwrite prior reports and does not claim an application/Gateway pass.

The baseline for this synthetic one-sentence API Gateway task returned a concise 175-character `content` with 1,895 characters in the separate `thinking` field at 512 tokens. In the new direct probe with `think=false`, Ollama returned HTTP 200, `done_reason=stop`, and 242 generated tokens, but placed 1,378 characters in `content` and no separate `thinking` field. Inspection of the synthetic content showed analysis before the final answer. This makes `think=false` unsuitable as a fix in the tested local stack; no default/config was changed.

Local Ollama was `0.40.14`, model `qwen3:4b`, digest `359d7dd4bcdab3d86b87d73ac27966f4dbb9f5efdfcc75d34a8764a09474fae7`. The tested request bypassed Gateway/application. This is a single measurement, not a content-quality rate or human review.

The current Ollama API documentation describes a `think` field on chat requests, but that does not prove behavior for this older local build; the recorded local response is the evidence used here: [Ollama API docs](https://github.com/ollama/ollama/blob/main/docs/api.md).
