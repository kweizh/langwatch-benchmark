# Implement Client-Side Payload Filtering for Large Traces

## Background
LangWatch's collector endpoint enforces a strict 1MB body size limit on incoming JSON trace payloads. When tracing a RAG pipeline, retrieving large contexts (e.g., massive documents) can easily cause the trace payload to exceed this limit, resulting in a 413 Payload Too Large error and dropped traces. You have a Python script that traces a RAG pipeline, but it currently attempts to log a 2MB document into the span, which would fail in production.

## Requirements
- Modify the existing Python script `run.py` to implement client-side payload filtering.
- Manually truncate the retrieved document string to a maximum of 1000 characters before logging it to the active LangWatch span.
- Do not remove the tracing decorators or context managers.
- The script must not make any real OpenAI API calls or require an OpenAI API key.

## Implementation Hints
- Intercept the large document string before it is passed to `span.update()`.
- Use Python string slicing to truncate the text to 1000 characters.
- Ensure the LangWatch SDK is configured to send data to the local mock collector (this is already set up in the environment variables).

## Acceptance Criteria
- Project path: /home/user/myproject
- Ensure the script is executed and the trace artifacts exist.
- Log file: /home/user/myproject/payload.json
- The script must run successfully via the command `python3 run.py`.
- The mock collector will intercept the LangWatch trace and write the incoming JSON payload to `/home/user/myproject/payload.json`.
- The JSON payload must contain the span data, and the retrieved document string in the span's output must be exactly 1000 characters long (or less if the original was smaller, but the test uses a 2MB string).

