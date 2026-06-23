The LangWatch API ingestion gateway enforces a strict 1MB body size limit on incoming JSON trace payloads. When tracing Retrieval-Augmented Generation (RAG) pipelines, large retrieved contexts often exceed this limit, causing an `HTTP 413 Payload Too Large` error and silent trace drops. 

You need to implement a Python wrapper for a RAG retrieval span that automatically measures and truncates the logged document strings to under 500KB before they are attached to the span's output.

**Constraints:**
- The truncation must only apply to the data logged to LangWatch via `span.update()`. The actual documents passed to the LLM must remain unmodified.
- You must use the `@langwatch.trace()` and `with langwatch.span()` primitives.
- If the payload is under 500KB, it must remain entirely untouched.