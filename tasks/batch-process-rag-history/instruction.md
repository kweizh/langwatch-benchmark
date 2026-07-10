# Batch Process RAG History with Client-Side Evaluations

## Background
You need to backfill observability and evaluation data for historical RAG (Retrieval-Augmented Generation) interactions into LangWatch. You have a large CSV file containing past queries, retrieved contexts, and generated answers. Your task is to process this file, trace each interaction in LangWatch, and apply a custom client-side evaluation.

## Requirements
- Create a Python script `process_rag.py` that reads a CSV file containing `query`, `retrieved_context`, and `generated_answer` columns.
- For each row, create a LangWatch trace named `Batch_RAG_${run-id}`.
- Inside the trace, create a nested span named `Retrieval` of type `rag_retrieval`.
- Log the `query` and `retrieved_context` to the `Retrieval` span's inputs/outputs.
- Add a client-side custom evaluation to the `Retrieval` span named `exact_match_eval`.
  - The evaluation should pass (score 1.0) if the `generated_answer` is exactly found as a substring within the `retrieved_context`. Otherwise, it should fail (score 0.0).
- The script must successfully process the entire CSV file without crashing and output a summary JSON file with the total count of passed and failed evaluations.

## Implementation Hints
- Read the `run-id` from `/logs/artifacts/run-id` to use in your trace names and output files.
- The input CSV file may contain extremely large fields. Ensure your CSV parsing logic can handle fields larger than the default system limits.
- LangWatch's collector endpoint enforces a strict 1MB body size limit. To prevent payload rejection, you must manually truncate the `retrieved_context` string to a maximum of 10,000 characters before logging it to the LangWatch span.
- Use the `langwatch` Python SDK's `@langwatch.trace()`, `langwatch.span()`, and `add_evaluation()` primitives.
- Ensure you use `uv` to install `langwatch` and any other required Python packages.

## Acceptance Criteria
- Project path: /home/user/myproject
- Command: `python3 process_rag.py --input rag_history.csv --output summary_${run-id}.json`
- The output JSON file must match the following format:
  ```json
  {
    "total_processed": number,
    "total_passed": number,
    "total_failed": number
  }
  ```
- The script must successfully execute without any CSV field size limit errors or HTTP 413 Payload Too Large errors from LangWatch.

