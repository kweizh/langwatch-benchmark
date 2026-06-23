# Evaluation Dataset Research: LangWatch (langwatch.ai)

This deep-dive research document analyzes the LangWatch platform, its APIs, SDKs, and the open-source Scenario agent testing framework. This technical breakdown is structured to support the creation of robust evaluation datasets and benchmark tasks for AI coding agents.

---

## 1. Library Overview

### Description
[LangWatch](https://langwatch.ai/) is an all-in-one LLMops, observability, and evaluation platform. It enables development teams to track, monitor, guardrail, and evaluate LLM applications. LangWatch supports real-time production observability, prompt management with versioning, offline batch evaluation experiments, and multi-turn agent simulation testing.

### Ecosystem Role
LangWatch acts as a central control plane for LLM pipelines and AI agents, sitting between developers, product managers, and production LLM runtimes. It is built on OpenTelemetry (OTel) standards, allowing it to seamlessly ingest traces from any OTel-compliant system or framework (e.g., Vercel AI SDK, LangChain, CrewAI, Instructor, DSPy, LiteLLM) and export telemetry without vendor lock-in.

### Project Setup (Non-Interactive)
To initialize and configure LangWatch in a non-interactive environment (such as a CI/CD pipeline or Docker container), developers use standard environment variables and package managers:

#### 1. Installation
Depending on the language stack, install the core LangWatch SDK and Scenario testing framework:
```bash
# Python
pip install langwatch langwatch-scenario pytest

# Node.js / TypeScript
npm install langwatch @langwatch/scenario vitest
```

#### 2. Environment Configuration
To run non-interactively, set the following environment variables in your shell or `.env` file. The SDKs automatically read these variables at startup:
```bash
export LANGWATCH_API_KEY="sk-lw-your-api-key"
export LANGWATCH_ENDPOINT="https://app.langwatch.ai" # Defaults to LangWatch Cloud
export LANGWATCH_PROJECT_ID="your-project-id"        # Required when using service-scoped API keys
```

#### 3. Local Prompt Scaffolding (CLI)
To initialize and manage prompts locally without using the interactive Web UI, install and run the LangWatch CLI tool to scaffold prompt configuration files:
```bash
# Initialize a local prompt repository structure
npx langwatch init --non-interactive

# Create a new prompt definition file locally
npx langwatch prompt create customer-support-bot --non-interactive
```
This generates a `./prompts/customer-support-bot.prompt.yaml` file and adds it to `./prompts/prompts.json` for local tracking and offline execution fallback.

---

## 2. Core Primitives & APIs

LangWatch's platform is divided into four main functional areas: **Observability/Tracing**, **Prompt Management**, **Evaluations & Guardrails**, and **Agent Simulations (Scenario)**.

### API Reference Index

* **Observability & Tracing**
  * [Python SDK Reference](https://langwatch.ai/docs/integration/python/reference): Setup, `@langwatch.trace()`, `@langwatch.span()`, trace/span context managers.
  * [TypeScript SDK Reference](https://langwatch.ai/docs/integration/typescript/reference): `setupObservability()`, `getLangWatchTracer()`, `tracer.withActiveSpan()`.
  * [Go SDK Reference](https://langwatch.ai/docs/integration/go/reference): `langwatch.Setup()`, `langwatch.Tracer()`, `tracer.Start()`.
* **Prompt Management**
  * [Prompt Management Overview](https://langwatch.ai/docs/prompt-management/getting-started): Fetching, compiling, and versioning prompts.
  * [Prompts CLI](https://langwatch.ai/docs/prompt-management/cli): Syncing and materializing prompts locally.
  * [Guaranteed Availability](https://langwatch.ai/docs/prompt-management/features/advanced/guaranteed-availability): Local prompt caching and fallback behavior.
* **Evaluations & Guardrails**
  * [Capturing Evaluations Guide](https://langwatch.ai/docs/integration/python/tutorials/capturing-evaluations-guardrails): Adding custom evaluations to active traces and spans.
  * [Experiments via SDK](https://langwatch.ai/docs/evaluations/experiments/sdk): Programmatic offline batch evaluation loops.
  * [Built-in Evaluators Index](https://langwatch.ai/docs/api-reference/evaluators/overview): RAG quality (RAGAS), safety, quality aspects, and LLM-as-a-judge.
* **Agent Simulations (Scenario)**
  * [Getting Started with Simulations](https://langwatch.ai/docs/agent-simulations/getting-started): Setting up multi-turn agent tests.
  * [Scenario Testing Framework](https://langwatch.ai/scenario/): Core concepts of the `scenario` library.
  * [Scenario API Documentation](https://langwatch.ai/scenario/reference/python/scenario/): Detailed Python classes and functions.
  * [TypeScript Scenario Reference](https://langwatch.ai/scenario/reference/javascript/scenario/): Detailed JS/TS classes and functions.

---

### Detailed Primitives and Code Examples

#### 1. Core Observability & Tracing
Traces capture the end-to-end execution flow of an LLM request, while Spans represent individual operations inside that flow (e.g., database queries, prompt formatting, LLM completions, or RAG retrievals).

##### Python SDK Implementation
```python
import os
import langwatch
from langwatch.instrumentors import OpenAIInstrumentor
from openai import OpenAI

# 1. Initialize LangWatch with automatic OpenAI instrumentation
langwatch.setup(
    api_key=os.getenv("LANGWATCH_API_KEY"),
    instrumentors=[OpenAIInstrumentor()]
)

# 2. Trace end-to-end user requests using decorators or context managers
@langwatch.trace(name="Customer Support Flow", metadata={"user_id": "usr_9981"})
def handle_customer_request(user_query: str):
    # Access the active trace context
    trace = langwatch.get_current_trace()
    trace.update(metadata={"session_id": "sess_abc123"})
    
    # Create a nested span for the retrieval step
    with langwatch.span(name="Document Retrieval", type="rag_retrieval") as span:
        # Simulate document lookup
        retrieved_docs = ["Doc 1: Reset password by clicking settings.", "Doc 2: Contact support if locked out."]
        span.update(
            input={"query": user_query},
            output={"documents": retrieved_docs}
        )
    
    # Create OpenAI client (calls are automatically captured via OpenAIInstrumentor)
    client = OpenAI()
    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": f"Use this context to answer: {retrieved_docs}"},
            {"role": "user", "content": user_query}
        ]
    )
    
    # Return result
    return response.choices[0].message.content
```

##### TypeScript SDK Equivalent
```typescript
import { setupObservability } from "langwatch/observability/node";
import { getLangWatchTracer } from "langwatch";
import { OpenAI } from "openai";

// Initialize observability
setupObservability({
  langwatch: { apiKey: process.env.LANGWATCH_API_KEY },
  serviceName: "customer-support-service"
});

const tracer = getLangWatchTracer("customer-support-service");
const openai = new OpenAI();

async function handleCustomerRequest(userQuery: string) {
  // Execute within active trace span
  return tracer.withActiveSpan("Customer Support Flow", async (traceSpan) => {
    traceSpan.setAttributes({ "user_id": "usr_9981", "session_id": "sess_abc123" });

    // Nested retrieval span
    const retrievedDocs = await tracer.withActiveSpan("Document Retrieval", async (span) => {
      span.setAttributes({ "langwatch.span.type": "rag_retrieval" });
      const docs = ["Doc 1: Reset password by clicking settings."];
      span.setAttributes({ "langwatch.inputs": JSON.stringify({ query: userQuery }) });
      span.setAttributes({ "langwatch.outputs": JSON.stringify({ documents: docs }) });
      return docs;
    });

    // LLM call (automatically instrumented if using OpenTelemetry-native integrations)
    const response = await openai.chat.completions.create({
      model: "gpt-4o",
      messages: [
        { role: "system", content: `Context: ${retrievedDocs.join(" ")}` },
        { role: "user", content: userQuery }
      ]
    });

    return response.choices[0].message.content;
  });
}
```

##### Go SDK Equivalent
```go
package main

import (
	"context"
	"log"
	langwatch "github.com/langwatch/langwatch/sdk-go"
	otelopenai "github.com/langwatch/langwatch/sdk-go/instrumentation/openai"
	"github.com/openai/openai-go"
	oaioption "github.com/openai/openai-go/option"
	"go.opentelemetry.io/otel"
	sdktrace "go.opentelemetry.io/otel/sdk/trace"
)

func main() {
	ctx := context.Background()

	// 1. Setup LangWatch exporter
	exporter, err := langwatch.NewDefaultExporter(ctx)
	if err != nil {
		log.Fatalf("failed to create exporter: %v", err)
	}

	tp := sdktrace.NewTracerProvider(sdktrace.WithBatcher(exporter))
	otel.SetTracerProvider(tp)

	// 2. Wrap OpenAI Client with middleware
	client := openai.NewClient(
		oaioption.WithMiddleware(otelopenai.Middleware()),
	)

	// 3. Create a trace
	tracer := langwatch.Tracer("my-service")
	ctx, span := tracer.Start(ctx, "CustomerSupportFlow")
	defer span.End()

	// Run OpenAI API calls within context to link them to the trace
	_, _ = client.Chat.Completions.New(ctx, openai.ChatCompletionNewParams{
		Model: openai.F(openai.ChatModelGPT4o),
		Messages: openai.F([]openai.ChatCompletionMessageParamUnion{
			openai.UserMessage("How do I reset my password?"),
		}),
	})
}
```

---

#### 2. Prompt Management
The Prompts API allows fetching versioned prompt templates from LangWatch, compiling dynamic variables, and automatically linking executions to traces. It also supports local materialization for reliable offline fallback.

##### Python SDK Implementation
```python
import langwatch
from litellm import completion

# Setup LangWatch (reads local materialized YAML prompts under ./prompts/.materialized/ if available)
langwatch.setup()

def generate_response(user_name: str, issue_description: str):
    # Retrieve the configured prompt by handle (and optionally, version)
    prompt = langwatch.prompts.get("customer-support-bot", version=3)
    
    # Compile the prompt with dynamic template variables (e.g. {{user_name}}, {{issue}})
    compiled_prompt = prompt.compile(
        user_name=user_name,
        issue=issue_description
    )
    
    # Execute completion. prompt.model and compiled_prompt.messages are passed dynamically
    response = completion(
        model=prompt.model,  # e.g., "openai/gpt-4o"
        messages=compiled_prompt.messages
    )
    
    return response.choices[0].message.content
```

##### TypeScript SDK Equivalent
```typescript
import { LangWatch } from "langwatch";
import { generateText } from "ai";
import { openai } from "@ai-sdk/openai";

const langwatch = new LangWatch({ apiKey: process.env.LANGWATCH_API_KEY });

async function generateResponse(userName: string, issueDescription: string) {
  // Fetch prompt from LangWatch
  const prompt = await langwatch.prompts.get("customer-support-bot");

  // Compile prompt with variables
  const compiledPrompt = prompt.compile({
    user_name: userName,
    issue: issueDescription,
  });

  // Execute using Vercel AI SDK
  const result = await generateText({
    model: openai(prompt.model.replace("openai/", "")),
    messages: compiledPrompt.messages,
  });

  return result.text;
}
```

---

#### 3. Agent Simulations (Scenario Framework)
`scenario` is an open-source framework developed by LangWatch to test AI agents. It uses AI agents (User Simulators and Judges) to perform dynamic, multi-turn conversation testing instead of static, rigid input-output assertions.

##### Python SDK Integration with Pytest
```python
import pytest
import scenario

# 1. Create an Adapter to connect your existing agent to the Scenario testing framework
class HelpdeskAgentAdapter(scenario.AgentAdapter):
    async def call(self, input: scenario.AgentInput) -> scenario.AgentReturnTypes:
        # Retrieve the conversation history from the simulator
        messages = input.messages
        last_user_message = input.last_new_user_message_str()
        
        # Call your actual underlying agent logic here
        agent_reply = f"Hello, I can help you with: {last_user_message}"
        
        # Return the response as a string, OpenAI message, or list of messages
        return agent_reply

# 2. Write the multi-turn agent test case with pytest
@pytest.mark.agent_test
@pytest.mark.asyncio
async def test_helpdesk_agent_scenario():
    agent = HelpdeskAgentAdapter()
    
    # Run the dynamic multi-turn conversation simulation
    result = await scenario.run(
        name="billing inquiry escalation test",
        description="The user has a billing issue and wants to speak to a manager if not resolved.",
        set_id="helpdesk-billing-suite",
        agents=[
            agent,
            # Simulator acts as a frustrated customer
            scenario.UserSimulatorAgent(
                system_prompt="You are a frustrated customer with a double billing issue. Insist on talking to a manager if the agent does not offer a refund."
            ),
            # Judge evaluates the conversation quality and criteria
            scenario.JudgeAgent(criteria=[
                "The agent must remain highly professional and polite throughout.",
                "The agent must escalate the ticket to a manager if the customer requests it."
            ])
        ],
        # Define the conversation script flow (empty script means fully dynamic conversation)
        script=[
            scenario.user("I was charged twice this month! Fix this now."),
            scenario.agent(),
            scenario.proceed(turns=3), # Let the simulator and agent converse dynamically for up to 3 turns
            scenario.succeed()         # Trigger success evaluation
        ]
    )
    
    # Assert that the JudgeAgent marked the conversation as successful
    assert result.success, f"Test failed. Reason: {result.reasoning}"
```

##### TypeScript SDK Integration with Vitest
```typescript
import { describe, it, expect } from "vitest";
import scenario, { type AgentAdapter, type AgentInput } from "@langwatch/scenario";

class SupportAgentAdapter implements AgentAdapter {
  async call(input: AgentInput) {
    const lastUserMessage = input.lastNewUserMessageStr();
    return `Let me help you with ${lastUserMessage}`;
  }
}

describe("Support Agent Test Suite", () => {
  it("should handle refund requests and escalate correctly", async () => {
    const agent = new SupportAgentAdapter();

    const result = await scenario.run({
      name: "Refund Request Scenario",
      description: "User asks for a refund on a subscription.",
      set_id: "refund-suite",
      agents: [
        agent,
        scenario.userSimulatorAgent(),
        scenario.judgeAgent({
          criteria: ["The agent must explain the refund policy clearly."]
        })
      ],
      script: [
        scenario.user("I need a refund for my subscription."),
        scenario.agent(),
        scenario.succeed()
      ]
    });

    expect(result.success).toBe(true);
  });
});
```

---

#### 4. Programmatic Evaluations
Developers can log custom client-side evaluation scores directly to active traces, or run server-side managed evaluation loops over offline datasets.

##### Client-Side Custom Evaluations (Python)
```python
import langwatch

@langwatch.trace(name="RAG Pipeline")
def run_rag_pipeline(question: str):
    # ... execution logic ...
    answer = "The capital of France is Paris."
    retrieved_context = "Paris is the capital and most populous city of France."
    
    # Log custom evaluation score directly to the current span
    langwatch.get_current_span().add_evaluation(
        name="groundedness_score",
        passed=True,
        score=0.98,
        label="fully_grounded",
        details="Output matches retrieved context with high semantic overlap."
    )
    return answer
```

##### Server-Side Offline Batch Evaluations (Python)
```python
import langwatch

# 1. Fetch evaluation dataset from LangWatch
dataset = langwatch.dataset.get_dataset("dataset-customer-queries")
df = dataset.to_pandas()

# 2. Initialize an evaluation run
evaluation = langwatch.evaluation.init("rag-accuracy-experiment")

# 3. Loop over records and execute evaluators
for index, row in evaluation.loop(df.iterrows()):
    # Run your production pipeline
    output = run_rag_pipeline(row["input"])
    
    # Run the built-in RAGAS context utilization evaluator on the LangWatch backend
    evaluation.run(
        "legacy/ragas_context_utilization",
        index=index,
        data={
            "input": row["input"],
            "output": output,
            "contexts": [row["context"]],
        }
    )
```

---

## 3. Real-World Use Cases & Templates

### Showcase Examples & Integration Patterns

1. **Vercel AI SDK Integration**: 
   LangWatch offers a native OpenTelemetry exporter package for TypeScript applications using Vercel's AI SDK. Messages, streaming tokens, tool calls, and model outputs are automatically traced and pushed to the LangWatch dashboard.
   * [Vercel AI SDK Integration Guide & Example](https://github.com/langwatch/langwatch/blob/main/typescript-sdk/example/lib/chat/vercel-ai.tsx)

2. **DSPy Optimization & Visualization**:
   LangWatch integrates with the DSPy framework to visualize the prompt optimization compilation process. It tracks the training steps, bootstrap few-shot iterations, and model generation scores.
   * [DSPy Visualization Quickstart](https://langwatch.ai/docs/dspy-visualization/quickstart)

3. **Multi-Turn Agent Simulations (Red-Teaming)**:
   The `scenario` framework is used to build adversarial "red-teaming" simulations where a specialized Red-Team agent (using strategies like Crescendo) attempts to extract system prompts or bypass safety guardrails.
   * [LLM Red-Teaming with Scenario](https://langwatch.ai/llm-red-teaming)

4. **CrewAI Multi-Agent Tracing**:
   Using the CrewAI OpenInference instrumentor, LangWatch can automatically trace complex multi-agent workflows, showing agent-to-agent task delegation, tool executions, and final outputs in a nested hierarchical tree.
   * [CrewAI Instrumentation Guide](https://langwatch.ai/docs/integration/python/integrations/crew-ai)

---

## 4. Developer Friction Points

### 1. Pydantic Serialization Error in `langwatch.dspy`
* **Description**: A serialization failure occurs when attempting to trace DSPy programs using Pydantic models (such as `BootstrapFewShot` or custom structured schemas).
* **Symptom / Error String**:
  ```
  TypeError: 'MockValSer' object cannot be converted to 'SchemaSerializer'
  ```
* **Underlying Cause**: The `SerializableAndPydanticEncoder` in `langwatch/dspy/__init__.py` serializes Pydantic `BaseModel` objects by executing `o.model_dump(exclude_unset=True)`. This delegates serialization to Pydantic's internal high-performance serializer, which fails because it is unaware of how to serialize non-Pydantic types (like `dspy.Predict` or custom framework objects) that are nested within the models.
* **Resolution**: Intercept Pydantic models in the encoder and serialize their fields manually using custom encoders, or bypass `model_dump()` for nested non-Pydantic objects.
* **Link**: [GitHub Issue #468](https://github.com/langwatch/langwatch/issues/468)

### 2. Collector Endpoint Refusing Large Payloads (>1MB)
* **Description**: Traces containing large retrieved contexts (RAG), extensive system instructions, or long multi-turn conversation histories fail to upload.
* **Symptom / Error String**:
  ```
  HTTP 413 Payload Too Large
  ```
  Or silent trace drop with warnings in the SDK logs about `/api/collector` refusing the body.
* **Underlying Cause**: The LangWatch API ingestion gateway enforces a strict 1MB body size limit on incoming JSON trace payloads. Large chunks of retrieved documents or massive serialized tool schemas easily exceed this limit.
* **Resolution**: Configure client-side payload filtering using the `dataCapture` callback in the TypeScript SDK to exclude large parameters, or manually truncate retrieved document strings in Python before logging them to the active span. For self-hosted instances, adjust the reverse proxy and collector server limits.
* **Link**: [GitHub Issue #512](https://github.com/langwatch/langwatch/issues/512)

### 3. DSPy Visualizer Crash with Unsupported Optimizers
* **Description**: Integrating the LangWatch DSPy tracker with certain optimizers (like `SIMBA`) causes the initialization to throw an unhandled exception.
* **Symptom / Error String**:
  ```
  ValueError: Optimizer SIMBA is not supported by LangWatch DSPy visualizer yet, only [BootstrapFewShot, BootstrapFewShotWithRandomSearch, COPRO, MIPROv2] are supported, please open an issue...
  ```
* **Underlying Cause**: The LangWatch DSPy visualizer explicitly checks and restricts the list of supported optimizers, failing with a `ValueError` if `SIMBA` (or other unsupported optimizers) is used.
* **Resolution**: Use supported optimizers like `BootstrapFewShotWithRandomSearch` or `MIPROv2`, or extend the visualizer's parser to support SIMBA.
* **Link**: [GitHub Issue #496](https://github.com/langwatch/langwatch/issues/496)

---

## 5. Evaluation Ideas

Below is a categorized list of high-level evaluation ideas designed to test an autonomous coding agent's ability to implement, configure, and debug LangWatch and Scenario integrations.

### Category: Tracing & Observability
* **[Simple] Custom Metadata Capture**: Instrument a standard Python LLM application to capture and log trace-level metadata (`user_id`, `session_id`) and custom span attributes.
* **[Medium] Hierarchical Multi-Span Tracing**: Implement a multi-step RAG pipeline in TypeScript, ensuring that prompt formatting, document retrieval, and LLM call spans are correctly nested and typed using manual OpenTelemetry span management.
* **[Complex] OpenTelemetry Integration & Filtering**: Configure LangWatch alongside an existing global OpenTelemetry TracerProvider, applying custom `span_exclude_rules` to prevent specific internal health-check or database spans from being exported to LangWatch.

### Category: Prompt Management
* **[Simple] Dynamic Prompt Compiler**: Implement a Python script that retrieves a versioned prompt from LangWatch, compiles it with dynamic user variables, and executes it via the LiteLLM library.
* **[Medium] Prompt A/B Testing Switcher**: Set up a TypeScript runtime system that dynamically selects between multiple prompt versions (variants) using random sampling, executes the call, and logs the chosen version back to LangWatch to enable variant performance tracking.
* **[Complex] Local Materialization Fallback**: Configure a CI/CD pipeline step that uses the Prompts CLI to materialize prompts locally as YAML files, and implement a robust fallback loader in the application that reads from the local cache when the LangWatch API is unreachable.

### Category: Agent Simulations (Scenario)
* **[Simple] Single-Turn Agent Adapter**: Create a basic `AgentAdapter` in Python for an existing chatbot and write a simple scenario test that asserts the agent responds to a greeting.
* **[Medium] Multi-Turn Support Simulation**: Implement a multi-turn customer support simulation using the `scenario` framework with a `UserSimulatorAgent` acting as an angry customer demanding a refund, and a `JudgeAgent` validating that the agent successfully escalates the ticket.
* **[Complex] Adversarial Red-Teaming Simulator**: Build an advanced red-teaming test suite using the `RedTeamAgent.crescendo` strategy to simulate a prompt injection attack, asserting that the agent never reveals its system prompt over 10 conversational turns.

---

## 6. Sources

1. [LangWatch Official Website](https://langwatch.ai/): Core platform landing page and documentation hub.
2. [LangWatch Documentation Index (llms.txt)](https://langwatch.ai/docs/llms.txt): High-density documentation index listing all available API guides and references.
3. [LangWatch GitHub Repository](https://github.com/langwatch/langwatch): Main repository for the platform, self-hosting guides, and SDKs.
4. [Scenario Agent Testing Framework](https://langwatch.ai/scenario/): Landing page and concepts overview for the Scenario framework.
5. [Scenario GitHub Repository](https://github.com/langwatch/scenario): Source code and reference implementations for the open-source Scenario library.
6. [Python SDK API Reference](https://langwatch.ai/docs/integration/python/reference): Python setup, tracing, prompts, and evaluations reference.
7. [TypeScript SDK API Reference](https://langwatch.ai/docs/integration/typescript/reference): TypeScript setup, tracing, and prompt reference.
8. [Go SDK API Reference](https://langwatch.ai/docs/integration/go/reference): Go setup, tracing, and middleware reference.
9. [GitHub Issue #468](https://github.com/langwatch/langwatch/issues/468): Detailed bug report regarding Pydantic serialization errors in `langwatch.dspy`.
10. [GitHub Issue #496](https://github.com/langwatch/langwatch/issues/496): Feature request and bug details about unsupported optimizers in the DSPy visualizer.
11. [GitHub Issue #512](https://github.com/langwatch/langwatch/issues/512): Bug report regarding body size limits on the `/api/collector` endpoint.
12. [Vercel AI SDK Integration Guide](https://github.com/langwatch/langwatch/blob/main/typescript-sdk/example/lib/chat/vercel-ai.tsx): Example project demonstrating full-stack tracing with the Vercel AI SDK.
