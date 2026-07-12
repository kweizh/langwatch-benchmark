/**
 * run.ts — Vercel AI SDK + LangWatch observability with client-side telemetry filtering.
 *
 * Usage:  npx tsx run.ts --prompt "Hello SECRET_TOKEN"
 *
 * Any occurrence of the exact string SECRET_TOKEN is replaced with [REDACTED] in
 * every OpenTelemetry span attribute before the payload reaches the LangWatch
 * collector endpoint.
 */

import { generateText } from "ai";
import type {
  LanguageModelV1,
  LanguageModelV1CallOptions,
} from "@ai-sdk/provider";
import {
  BasicTracerProvider,
  BatchSpanProcessor,
  SimpleSpanProcessor,
} from "@opentelemetry/sdk-trace-base";
import type {
  SpanProcessor,
  ReadableSpan,
  Span as OtelSpan,
} from "@opentelemetry/sdk-trace-base";
import type { Context } from "@opentelemetry/api";
import { trace } from "@opentelemetry/api";
import { LangWatchExporter } from "langwatch";

// ---------------------------------------------------------------------------
// 1. Parse CLI arguments
// ---------------------------------------------------------------------------
const args = process.argv.slice(2);
const promptIndex = args.indexOf("--prompt");
if (promptIndex === -1 || !args[promptIndex + 1]) {
  console.error("Usage: npx tsx run.ts --prompt <text>");
  process.exit(1);
}
const userPrompt = args[promptIndex + 1];

// ---------------------------------------------------------------------------
// 2. Minimal mock LanguageModelV1 provider (no real API key required)
//    Echoes the prompt text back as the generated "response".
// ---------------------------------------------------------------------------
const mockProvider: LanguageModelV1 = {
  specificationVersion: "v1",
  provider: "mock",
  modelId: "mock-echo",
  defaultObjectGenerationMode: undefined,

  async doGenerate(options: LanguageModelV1CallOptions) {
    // Extract the user prompt text from the messages
    let inputText = "";
    for (const msg of options.prompt) {
      if (msg.role === "user") {
        for (const part of msg.content) {
          if (part.type === "text") {
            inputText += part.text;
          }
        }
      }
    }
    const responseText = `Echo: ${inputText}`;
    return {
      text: responseText,
      finishReason: "stop" as const,
      usage: { promptTokens: 10, completionTokens: 10 },
      rawCall: { rawPrompt: inputText, rawSettings: {} },
    };
  },

  async doStream(options: LanguageModelV1CallOptions) {
    // Minimal streaming implementation (not used by generateText, but required by interface)
    let inputText = "";
    for (const msg of options.prompt) {
      if (msg.role === "user") {
        for (const part of msg.content) {
          if (part.type === "text") {
            inputText += part.text;
          }
        }
      }
    }
    const responseText = `Echo: ${inputText}`;
    async function* gen() {
      yield { type: "text-delta" as const, textDelta: responseText };
      yield {
        type: "finish" as const,
        finishReason: "stop" as const,
        usage: { promptTokens: 10, completionTokens: 10 },
      };
    }
    return {
      stream: gen() as any,
      rawCall: { rawPrompt: inputText, rawSettings: {} },
    };
  },
};

// ---------------------------------------------------------------------------
// 3. Redacting span processor — wraps any downstream SpanProcessor and
//    replaces every occurrence of SECRET_TOKEN with [REDACTED] in all
//    span attribute string values before they are forwarded.
// ---------------------------------------------------------------------------
const SENSITIVE = "SECRET_TOKEN";
const REDACTED = "[REDACTED]";

function redactValue(value: unknown): unknown {
  if (typeof value === "string") {
    return value.split(SENSITIVE).join(REDACTED);
  }
  return value;
}

function redactAttributes(attributes: Record<string, unknown>): void {
  for (const key of Object.keys(attributes)) {
    const val = attributes[key];
    if (typeof val === "string" && val.includes(SENSITIVE)) {
      attributes[key] = redactValue(val);
    } else if (Array.isArray(val)) {
      attributes[key] = val.map((item) =>
        typeof item === "string" ? redactValue(item) : item
      );
    }
  }
}

class RedactingSpanProcessor implements SpanProcessor {
  constructor(private readonly downstream: SpanProcessor) {}

  onStart(span: OtelSpan, parentContext: Context): void {
    this.downstream.onStart(span, parentContext);
  }

  onEnd(span: ReadableSpan): void {
    // span.attributes is a plain object — mutate in place before forwarding
    redactAttributes(span.attributes as Record<string, unknown>);
    this.downstream.onEnd(span);
  }

  forceFlush(): Promise<void> {
    return this.downstream.forceFlush();
  }

  shutdown(): Promise<void> {
    return this.downstream.shutdown();
  }
}

// ---------------------------------------------------------------------------
// 4. Configure OpenTelemetry with LangWatch as the exporter
// ---------------------------------------------------------------------------
const langwatchExporter = new LangWatchExporter({
  endpoint: process.env.LANGWATCH_ENDPOINT ?? "http://localhost:5560",
  apiKey: process.env.LANGWATCH_API_KEY ?? "test-api-key",
  includeAllSpans: true,
});

const batchProcessor = new BatchSpanProcessor(langwatchExporter);
const redactingProcessor = new RedactingSpanProcessor(batchProcessor);

const provider = new BasicTracerProvider();
provider.addSpanProcessor(redactingProcessor);
provider.register(); // registers as the global OTel TracerProvider

// ---------------------------------------------------------------------------
// 5. Run generateText with experimental telemetry enabled
// ---------------------------------------------------------------------------
async function main() {
  console.log(`Prompt: ${userPrompt}`);

  const result = await generateText({
    model: mockProvider,
    prompt: userPrompt,
    experimental_telemetry: {
      isEnabled: true,
      functionId: "run-ts-demo",
      metadata: { promptPreview: userPrompt },
    },
  });

  console.log(`Generated text: ${result.text}`);

  // Flush all buffered spans to the LangWatch endpoint
  try {
    await provider.forceFlush();
    await provider.shutdown();
  } catch {
    // Export errors are non-fatal; the LangWatchExporter already logs them.
  }
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
