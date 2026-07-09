# LangWatch: Run a Built-in LLM-as-a-Judge Evaluator and Attach the Verdict to the Trace

## Background
You are building a Python question-answering pipeline and want an automated quality gate that does not rely on a golden answer. LangWatch ships a library of **server-side built-in evaluators**, including an **LLM-as-a-Judge** family that scores a produced answer against a **custom rubric/criteria** you supply. Unlike a client-side heuristic, this evaluator runs on the LangWatch backend: your code sends the question, the generated answer, and the retrieved contexts to the evaluators API, the judge returns a `passed`/`score`/`label`/`details` verdict, and LangWatch records that verdict as an evaluation on the active trace.

Your job is to build the pipeline, invoke the built-in **LLM-as-a-Judge Boolean** evaluator against your produced answer with a custom rubric, and make sure the returned verdict is both captured by your code and attached to the answer-generation span of the trace.

## Requirements
Work inside the Python project at `/home/user/project`. Implement a module named `qa_pipeline.py` at the project root exposing these callables:

- `retrieve(question: str) -> list[str]`: Deterministically retrieve context passages for `question` from a fixed in-code corpus. Retrieval MUST be a pure function of the question and corpus (no randomness, no network).
- `run_pipeline(question: str) -> dict`: Run the end-to-end pipeline under a LangWatch trace, emit the spans described below, generate an answer grounded in the retrieved contexts, run the built-in LLM-as-a-Judge evaluator on that answer while the answer-generation span is active, capture the returned verdict, persist it, and return a dict.

Also provide a CLI entrypoint `main.py`.

### Span layout
- The trace root span must be named `qa_pipeline`.
- Context retrieval happens in a child span named `retrieve_context`.
- Answer generation happens in a child span named `generate_answer`. No live LLM/network call is required to produce the answer — a deterministic answer derived from the retrieved contexts is acceptable (this task is about wiring the built-in evaluator, not answer quality).

### Evaluator invocation
- While the `generate_answer` span is the currently active span, invoke LangWatch's **built-in LLM-as-a-Judge Boolean** evaluator (evaluator slug `langevals/llm_boolean`) through the LangWatch evaluations API so the evaluation runs on the backend and is bound to the active trace.
- The evaluator must receive a data object containing the `input` (the question), the `output` (your produced answer), and the `contexts` (the retrieved passages as a list).
- The evaluator must be configured with a **custom rubric** passed through the evaluator `settings` (the judge prompt/criteria). The rubric must encode the pass criteria: the answer should be faithful to the provided context AND directly address the user's question.
- Use the evaluation name `answer-quality-judge`.
- Capture the verdict returned by the evaluator (`passed`, `score`, `label`, `details`) and use exactly those returned values — do not recompute or hardcode them locally.

### Recording the verdict
- `run_pipeline` must return a dict of the form `{"answer": <str>, "judgement": {"passed": <bool>, "score": <number>, "label": <str>, "details": <str>}}`, where the `judgement` fields are exactly the values returned by the evaluator.
- `run_pipeline` must also write those same fields to `/home/user/project/judge_result.json`.
- Read the LangWatch API key and endpoint from the environment (`LANGWATCH_API_KEY`, `LANGWATCH_ENDPOINT`). Do not hardcode credentials.

## Implementation Hints
- Install all Python dependencies with `uv` inside a virtual environment (some LangWatch-related packages misbehave with the system pip). LangWatch pulls in the OpenTelemetry SDK and OTLP/HTTP exporter transitively.
- Initialize the SDK with `langwatch.setup(...)`, reading the API key and endpoint from the environment.
- The evaluations API creates an evaluation span attached to the current trace context, POSTs to the LangWatch backend, and returns a result object exposing `status`, `passed`, `score`, `label`, and `details`. Invoking it from inside the `generate_answer` span is what binds the verdict to the correct span.
- Built-in evaluators are addressed by slug; the LLM-as-a-Judge Boolean evaluator's slug is `langevals/llm_boolean`. Evaluator-specific configuration (such as the judge rubric/prompt) is passed via the `settings` argument, while the message data (`input`, `output`, `contexts`) is passed via the `data` argument.
- LangWatch exports spans over a batching processor; ensure spans are flushed before the process exits so nothing is lost.
- Keep `retrieve` pure and deterministic so the same question always yields the same contexts.
- SDK progress/log output may be interleaved on stdout; since the verdict is persisted to a JSON artifact, keep that file strictly machine-readable.

## Acceptance Criteria
- Project path: /home/user/project
- Command: `python main.py "<question>"`
  - Input argument: a single free-text `<question>` string.
  - The stdout MUST contain a line in the format `Answer: <text>` where `<text>` is a non-empty string.
  - The stdout MUST contain a line in the format `Judgement: <passed> <score> <label>` reflecting the evaluator's returned verdict.
- Importable contract (used by the verifier), all in `qa_pipeline.py`:
  - `retrieve(question: str) -> list[str]` returns a non-empty, deterministic list of context strings.
  - `run_pipeline(question: str) -> dict` returns `{"answer": str, "judgement": {"passed": bool, "score": number, "label": str, "details": str}}`, emits spans `qa_pipeline`, `retrieve_context`, and `generate_answer`, and runs the built-in evaluator while `generate_answer` is active.
- Observable evaluator behavior (checked against requests the SDK sends to `POST {LANGWATCH_ENDPOINT}/api/evaluations/{slug}/evaluate`):
  - Exactly one call to the built-in LLM-as-a-Judge Boolean evaluator (the evaluator slug path contains `langevals/llm_boolean`).
  - The call's `data` object contains `input` equal to the question, `output` equal to the produced non-empty answer, and `contexts` as a non-empty JSON list.
  - The call carries a non-empty custom rubric in the evaluator `settings` that encodes the pass criteria (references both the provided context/faithfulness and directly answering the question).
  - The call is associated with the active trace (it carries a non-empty `trace_id`).
  - The evaluation `name` is `answer-quality-judge`.
- Observable recording behavior:
  - The verdict is exported as an evaluation-type span nested under the `generate_answer` span (checked on the spans LangWatch exports to `POST {LANGWATCH_ENDPOINT}/api/otel/v1/traces`).
  - `/home/user/project/judge_result.json` exists and its `passed`, `score`, `label`, and `details` equal exactly the values the evaluator returned (proven by the verdict tracking the evaluator's response rather than a fixed local value).
- Credentials and endpoint are read from `LANGWATCH_API_KEY` and `LANGWATCH_ENDPOINT`; no secrets are hardcoded. Python dependencies are installed with `uv`.

