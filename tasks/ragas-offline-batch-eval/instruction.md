# LangWatch: Server-Side Offline Batch RAG Evaluation with a Built-in RAGAS Evaluator

## Background
Your team ships a Retrieval-Augmented Generation (RAG) assistant and wants an offline, dataset-driven quality gate before every release. LangWatch provides an **SDK-driven batch evaluation** ("experiment") API: you initialize an evaluation run, loop over a dataset, run your production pipeline for each row, and hand the row's `input`, generated `output`, and retrieved `contexts` to a **built-in evaluator that runs on the LangWatch backend** (no need to host the metric yourself). LangWatch records the run and every evaluator result so the whole team can inspect scores over time.

You must wire up such a batch evaluation loop that drives a real RAG pipeline over a seeded dataset and invokes the built-in RAGAS **context-utilization** evaluator (`legacy/ragas_context_utilization`) on the backend for every row.

## Requirements
- Work inside the project at `/home/user/project`.
- Build a runnable script (`run_evaluation.py`) that performs the full offline batch evaluation end-to-end when executed.
- Read all credentials/endpoint configuration from the environment (`LANGWATCH_API_KEY`, `LANGWATCH_ENDPOINT`, `LANGWATCH_PROJECT_ID`). Never hardcode secrets.
- Load the seeded evaluation dataset from `data/qa_dataset.csv` (each row is one question to evaluate) and the retrieval corpus from `data/knowledge_base.json`.
- Implement a real, deterministic RAG pipeline (`retrieve` then `generate`): for each question, retrieve one or more relevant documents from the knowledge base to use as the `contexts`, then produce a non-empty answer `output` grounded in those contexts. A live LLM/network call is NOT required — the generation step may be deterministic/extractive — but the retrieved contexts must actually come from the knowledge base.
- Initialize a LangWatch **batch evaluation run** and iterate over **every** dataset row using the SDK's evaluation loop primitive.
- For each row, invoke the built-in evaluator `legacy/ragas_context_utilization` on the LangWatch backend, passing a data object that contains the row's `input` (the question), the pipeline's `output` (the answer), and the `contexts` (the retrieved documents as a list).
- Make the run name traceable and safe for concurrent runs: read the `run-id` from `/logs/artifacts/run-id` and include it in the evaluation run name.
- After the loop completes, write a machine-readable summary and print a human-readable completion line.

## Implementation Hints
- Install everything with `uv` inside a virtual environment (`uv venv` + `uv pip install ...`); some LangWatch dependencies misbehave under the system `pip`.
- The batch evaluation API is exposed under `langwatch.evaluation` (initialize a run, then wrap your dataset iterator with the loop helper so each row is tracked). Built-in evaluators are invoked per-row by slug and receive a `data` dict; some SDK versions also expect an evaluator `settings` dict, so check the signature.
- `contexts` must be a JSON list (e.g. a list of strings), not a single concatenated blob — the context-utilization metric compares the answer against the individual retrieved chunks.
- The pipeline can be traced for full visibility, but correctness here is about the evaluation run being created and every row being scored, not about a specific span layout.
- Log output from the SDK (progress bars, run URL) is mixed with your own output on stdout; if you emit structured results, write them to a file so they are not interleaved with SDK logs.
- Because credentials and endpoint come from the environment, the same script must work unchanged against LangWatch Cloud or any self-hosted/compatible endpoint.

## Acceptance Criteria
- Project path: /home/user/project
- Command: `python run_evaluation.py`
  - Reads `LANGWATCH_ENDPOINT`, `LANGWATCH_API_KEY`, and `LANGWATCH_PROJECT_ID` from the environment.
  - Reads the `run-id` from `/logs/artifacts/run-id` and includes it in the evaluation run name.
  - Exits with code 0 on success.
- Observable backend behavior (checked against the configured `LANGWATCH_ENDPOINT`):
  - Exactly one batch evaluation run is initialized (experiment type `BATCH_EVALUATION_V2`) whose name contains the `run-id`.
  - The built-in evaluator `legacy/ragas_context_utilization` is invoked once per dataset row (one evaluator call for every row in `data/qa_dataset.csv`).
  - Each evaluator call sends a `data` object containing: `input` (a non-empty string equal to that row's question), `output` (a non-empty string), and `contexts` (a non-empty JSON list of strings).
  - The set of `input` values across all evaluator calls equals the exact set of questions in the dataset (all rows evaluated, none skipped or duplicated).
- Output artifact: `/home/user/project/eval_summary.json`
  - A JSON object with fields: `experiment_name` (string, contains the `run-id`), `rows_evaluated` (integer, equal to the number of dataset rows), and `evaluator` (string, equal to `legacy/ragas_context_utilization`).
- Stdout must contain a line matching `Rows evaluated: <N>` where `<N>` is the number of dataset rows.

