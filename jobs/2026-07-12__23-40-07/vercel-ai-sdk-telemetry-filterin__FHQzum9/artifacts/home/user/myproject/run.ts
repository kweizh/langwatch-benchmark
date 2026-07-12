/* eslint-disable @typescript-eslint/no-explicit-any */
/**
 * Vercel AI SDK + LangWatch observability demo with client-side telemetry
 * filtering.
 *
 * What this script does:
 *  1. Parses a `--prompt` argument from the CLI.
 *  2. Initializes OpenTelemetry-based LangWatch observability for Node.js,
 *     wiring the SDK's LangWatchExporter behind a filtering wrapper exporter
 *     that scrubs any occurrence of `SECRET_TOKEN` to `[REDACTED]` from the
 *     outgoing payload.
 *  3. Implements a minimal mock Vercel AI SDK provider.
 *  4. Calls `generateText` with telemetry enabled so spans are exported.
 *  5. Flushes the tracer provider so the telemetry is sent to LangWatch
 *     before the process exits.
 *
 * Run with:
 *   npx tsx run.ts --prompt "Hello world with SECRET_TOKEN in it"
 */

import { generateText } from "ai";
import type { LanguageModelV1 } from "@ai-sdk/provider";
import { LangWatchExporter } from "langwatch";
import {
  BasicTracerProvider,
  SimpleSpanProcessor,
  InMemorySpanExporter,
  ReadableSpan,
} from "@opentelemetry/sdk-trace-base";
import { trace, type Tracer } from "@opentelemetry/api";

// Configuration
process.env.LANGWATCH_ENDPOINT ??= "http://127.0.0.1:9999";
process.env.LANGWATCH_API_KEY ??= "dummy-api-key-for-offline-run";

const LANGWATCH_ENDPOINT =
  process.env.LANGWATCH_ENDPOINT ?? "http://127.0.0.1:9999";
const LANGWATCH_API_KEY =
  process.env.LANGWATCH_API_KEY ?? "dummy-api-key-for-offline-run";

function parsePromptArg(): string {
  const argv = process.argv.slice(2);
  const idx = argv.findIndex(
    (a) => a === "--prompt" || a.startsWith("--prompt="),
  );
  if (idx === -1) {
    throw new Error("Missing required --prompt argument");
  }
  const raw = argv[idx];
  if (raw.startsWith("--prompt=")) {
    return raw.slice("--prompt=".length);
  }
  const value = argv[idx + 1];
  if (value === undefined) {
    throw new Error("--prompt was provided without a value");
  }
  return value;
}// ---------------------------------------------------------------------------
// Client-side payload filtering
// ---------------------------------------------------------------------------

const SENSITIVE_TOKEN = "SECRET_TOKEN";
const REDACTION_PLACEHOLDER = "[REDACTED]";

/**
 * Recursively walks a value and replaces every occurrence of `SECRET_TOKEN`
 * with `[REDACTED]` inside any string we find. Objects and arrays are
 * traversed, dates and other primitives are returned as-is.
 */
function redactValue(value: unknown): unknown {
  if (typeof value === "string") {
    return value.split(SENSITIVE_TOKEN).join(REDACTION_PLACEHOLDER);
  }
  if (Array.isArray(value)) {
    return value.map((v) => redactValue(v));
  }
  if (value && typeof value === "object") {
    const out: Record<string, unknown> = {};
    for (const [k, v] of Object.entries(value as Record<string, unknown>)) {
      out[k] = redactValue(v);
    }
    return out;
  }
  return value;
}

/**
 * Mutates a span so that its `attributes` field reflects the sanitized
 * values. The OTel SDK's `Span` class keeps a mutable `attributes` object
 * even though the public type marks it as readonly. Mutating it in-place
 * guarantees that every downstream serializer (OTLP transformer, etc.)
 * sees the redacted values without us having to reimplement the protobuf
 * encoding.
 */
function applyRedactionToSpan(span: ReadableSpan): ReadableSpan {
  const sanitized = redactValue(span.attributes ?? {}) as Record<string, unknown>;
  const anySpan = span as unknown as {
    attributes?: Record<string, unknown>;
  };
  if (anySpan.attributes && typeof anySpan.attributes === "object") {
    for (const key of Object.keys(anySpan.attributes)) {
      delete anySpan.attributes[key];
    }
    Object.assign(anySpan.attributes, sanitized);
  }
  return span;
}// ---------------------------------------------------------------------------
// Observability initialization
// ---------------------------------------------------------------------------

/**
 * A span-exporter wrapper that applies a `dataCapture`-style transform to
 * every span before forwarding it to the underlying exporter. This is the
 * LangWatch-compatible equivalent of the `dataCapture` callback used to
 * redact sensitive information before telemetry leaves the client.
 */
class FilteringSpanExporter {
  private readonly inner: any;
  public readonly dataCapture: (spans: ReadableSpan[]) => ReadableSpan[];
  public exportedPayloads: { serialized: string; spans: ReadableSpan[] }[] = [];

  constructor(params: {
    inner: any;
    dataCapture?: (spans: ReadableSpan[]) => ReadableSpan[];
  }) {
    this.inner = params.inner;
    this.dataCapture = params.dataCapture ?? ((spans) => spans);
  }

  export(spans: ReadableSpan[], resultCallback: (result: any) => void): void {
    const filtered = this.dataCapture(spans).map(applyRedactionToSpan);
    try {
      const serialized = JSON.stringify(
        filtered.map((s) => ({
          name: s.name,
          attributes: s.attributes,
        })),
      );
      this.exportedPayloads.push({ serialized, spans: filtered });
    } catch {
      // ignore serialization errors
    }
    this.inner.export(filtered, resultCallback);
  }

  async shutdown(): Promise<void> {
    if (typeof this.inner.shutdown === "function") {
      await this.inner.shutdown();
    }
  }

  async forceFlush(): Promise<void> {
    if (typeof this.inner.forceFlush === "function") {
      await this.inner.forceFlush();
    }
  }
}

/**
 * Initializes OpenTelemetry-based LangWatch observability for Node.js.
 *
 * Returns:
 *  - `provider`: the tracer provider used for AI SDK telemetry
 *  - `tracer`: a tracer the AI SDK can use via `experimental_telemetry.tracer`
 *  - `filteringExporter`: the wrapper exporter that redacts sensitive tokens
 *  - `memoryExporter`: in-memory exporter so we can verify the filter applied
 *  - `shutdown()`: flushes and shuts the provider down
 */
function setupObservability(): {
  provider: BasicTracerProvider;
  tracer: Tracer;
  filteringExporter: FilteringSpanExporter;
  memoryExporter: InMemorySpanExporter;
  shutdown: () => Promise<void>;
} {
  const langwatchExporter = new LangWatchExporter({
    endpoint: LANGWATCH_ENDPOINT,
    apiKey: LANGWATCH_API_KEY,
    debug: false,
  });

  const memoryExporter = new InMemorySpanExporter();

  // The dataCapture callback is the documented LangWatch hook for
  // payload-level filtering. We pass it through to the wrapper exporter so
  // users can plug in their own scrubbing logic if desired.
  const dataCapture = (spans: ReadableSpan[]): ReadableSpan[] => spans;

  const filteringExporter = new FilteringSpanExporter({
    inner: langwatchExporter,
    dataCapture,
  });

  const provider = new BasicTracerProvider();
  provider.addSpanProcessor(
    new SimpleSpanProcessor(filteringExporter as any),
  );
  provider.addSpanProcessor(new SimpleSpanProcessor(memoryExporter));

  provider.register();

  const tracer = trace.getTracer("langwatch-vercel-ai-sdk-demo");

  return {
    provider,
    tracer,
    filteringExporter,
    memoryExporter,
    shutdown: async () => {
      // Capture spans before shutdown because InMemorySpanExporter's shutdown
      // clears them.
      const spans = memoryExporter.getFinishedSpans();
      await provider.forceFlush();
      await provider.shutdown();
      return spans;
    },
  };
}// ---------------------------------------------------------------------------
// Mock Vercel AI SDK provider
// ---------------------------------------------------------------------------

/**
 * Extract the user's text from the prompt argument. The Vercel AI SDK accepts
 * either a string or an array of `LanguageModelV1Message` objects depending
 * on the entry point; we handle both for completeness.
 */
function extractPromptText(prompt: unknown): string {
  if (typeof prompt === "string") return prompt;
  if (Array.isArray(prompt)) {
    return prompt
      .map((part: any) => {
        if (typeof part === "string") return part;
        if (part && typeof part === "object" && "content" in part) {
          const content = (part as any).content;
          if (typeof content === "string") return content;
          if (Array.isArray(content)) {
            return content
              .map((c: any) => (typeof c === "string" ? c : c?.text ?? ""))
              .join(" ");
          }
        }
        if (part && typeof part === "object" && "text" in part) {
          return String((part as any).text ?? "");
        }
        return "";
      })
      .join(" ");
  }
  return "";
}

/**
 * A minimal `LanguageModelV1` implementation that echoes the prompt back as
 * the model's response. It exists so we can exercise the full telemetry
 * pipeline (and the redaction logic) without any real LLM API key.
 */
function createMockLanguageModel(): LanguageModelV1 {
  return {
    specificationVersion: "v1",
    provider: "mock-provider",
    modelId: "mock-echo-model",
    defaultObjectGenerationMode: undefined,

    async doGenerate(options: any) {
      const promptText = extractPromptText(options?.prompt);
      const reply = `Mock response to: ${promptText}`;
      return {
        text: reply,
        finishReason: "stop",
        usage: {
          promptTokens: promptText.length,
          completionTokens: reply.length,
        },
        rawCall: {
          rawPrompt: options?.prompt ?? null,
          rawSettings: {},
        },
        warnings: [],
      };
    },

    async doStream(options: any) {
      const promptText = extractPromptText(options?.prompt);
      const reply = `Mock response to: ${promptText}`;
      const stream = new ReadableStream<any>({
        start(controller) {
          controller.enqueue({ type: "response-metadata", id: "mock" });
          controller.enqueue({ type: "text-delta", textDelta: reply });
          controller.enqueue({
            type: "finish",
            finishReason: "stop",
            usage: {
              promptTokens: promptText.length,
              completionTokens: reply.length,
            },
          });
          controller.close();
        },
      });
      return {
        stream,
        rawCall: {
          rawPrompt: options?.prompt ?? null,
          rawSettings: {},
        },
      };
    },
  };
}// ---------------------------------------------------------------------------
// Main
// ---------------------------------------------------------------------------

async function main() {
  const prompt = parsePromptArg();

  const observability = setupObservability();

  try {
    const result = await generateText({
      model: createMockLanguageModel() as any,
      prompt,
      experimental_telemetry: {
        isEnabled: true,
        tracer: observability.tracer,
      },
    });

    // Print the generated text to stdout as required by the acceptance
    // criteria.
    process.stdout.write(`${result.text}\n`);

    // Force flush the tracer provider so all spans are exported BEFORE we
    // shut things down (the InMemorySpanExporter's shutdown clears its
    // finished spans, so we need to capture them first).
    const capturedSpans = observability.memoryExporter.getFinishedSpans();
    await observability.provider.forceFlush();
    await observability.provider.shutdown();

    // Verify the redaction worked on both the in-memory copy and the
    // payloads captured by the wrapper exporter.
    const leakedMemory = verifyNoSensitiveLeak(capturedSpans);
    const forwardedPayloads = observability.filteringExporter.exportedPayloads
      .map((p) => p.serialized)
      .join("\n");
    const leakedForwarded = forwardedPayloads.includes(SENSITIVE_TOKEN);

    if (leakedMemory.length > 0 || leakedForwarded) {
      process.stderr.write(
        `\n[run.ts] ERROR: SECRET_TOKEN leaked into exported telemetry.\n`,
      );
      for (const name of leakedMemory) {
        process.stderr.write(`  memoryExporter span: ${name}\n`);
      }
      if (leakedForwarded) {
        process.stderr.write(`  filteringExporter payload contains SECRET_TOKEN\n`);
      }
      process.exitCode = 1;
    } else {
      process.stderr.write(
        `\n[run.ts] Verified: SECRET_TOKEN redacted to [REDACTED] in all exported telemetry.\n`,
      );
    }
  } catch (err) {
    await observability.provider.shutdown().catch(() => {});
    throw err;
  }
}

function verifyNoSensitiveLeak(spans: ReadableSpan[]): string[] {
  const offending: string[] = [];
  for (const span of spans) {
    const serialized = JSON.stringify(span.attributes ?? {});
    if (serialized.includes(SENSITIVE_TOKEN)) {
      offending.push(span.name);
    }
  }
  return offending;
}

main().catch((err) => {
  process.stderr.write(`[run.ts] Failed: ${err}\n`);
  process.exit(1);
});