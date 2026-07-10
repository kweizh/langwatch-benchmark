# Vercel AI SDK Telemetry Filtering with LangWatch

## Background
When integrating Vercel AI SDK with LangWatch observability, you may encounter situations where traces contain sensitive information or exceed payload size limits. You need to implement client-side telemetry filtering to redact sensitive data before it is sent to the LangWatch collector.

## Requirements
- Create a TypeScript script `run.ts` that accepts a `--prompt` argument.
- Use the Vercel AI SDK (`generateText`) to generate a response based on the prompt.
- To avoid needing a real LLM API key, implement and use a simple mock Vercel AI SDK provider (e.g., a custom `LanguageModelV1` implementation) that simply echoes the prompt or returns a dummy string.
- Initialize LangWatch observability for Node.js.
- Configure client-side payload filtering using the `dataCapture` callback (or equivalent filtering mechanism in the LangWatch SDK) to redact any occurrence of the exact string `SECRET_TOKEN`, replacing it with `[REDACTED]` in the outgoing telemetry payloads.
- Ensure that the telemetry is flushed and sent to the LangWatch endpoint before the script exits.

## Implementation Hints
- Use `setupObservability` from `langwatch/observability/node`.
- Look into the LangWatch SDK configuration options to find the `dataCapture` callback or OpenTelemetry span processor filtering to modify span attributes before they are exported.
- Vercel AI SDK allows creating custom providers by implementing the `LanguageModelV1` interface. You can create a minimal mock provider to satisfy the `generateText` call without making real HTTP requests.
- Use `npx tsx run.ts` to execute the script.
- Make sure to properly await the completion of the LLM call and any telemetry flushing.

## Acceptance Criteria
- Project path: /home/user/myproject
- Command: `npx tsx run.ts --prompt <text>`
- The command must execute without errors and output the generated text.
- The command must not require or use a real OpenAI API key.
- The script must send OpenTelemetry traces to the configured `LANGWATCH_ENDPOINT`.
- The outgoing telemetry payload must not contain the string `SECRET_TOKEN`; it must be replaced with `[REDACTED]`.

