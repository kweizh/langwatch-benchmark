#!/usr/bin/env python3
"""Batch process RAG history with client-side evaluations for LangWatch.

Reads a CSV file containing query, retrieved_context, and generated_answer
columns. For each row, creates a LangWatch trace with a nested Retrieval span
and applies a client-side exact-match evaluation.
"""

import argparse
import csv
import json
import sys

# ---------------------------------------------------------------------------
# Increase the CSV field size limit so extremely large fields don't crash the
# parser.  sys.maxsize can raise OverflowError on some platforms, so we
# decrement until an acceptable value is found.
# ---------------------------------------------------------------------------
_max_field_size = sys.maxsize
while True:
    try:
        csv.field_size_limit(_max_field_size)
        break
    except OverflowError:
        _max_field_size = int(_max_field_size / 10)

import langwatch
from opentelemetry import trace as trace_api

# Maximum characters of retrieved_context to log to LangWatch.  The collector
# endpoint enforces a strict 1 MB body size limit, so we truncate to stay well
# under that threshold.
MAX_CONTEXT_LENGTH = 10_000

# Path to the run-id artifact file.
RUN_ID_PATH = "/logs/artifacts/run-id"


def read_run_id():
    """Read the run-id from /logs/artifacts/run-id."""
    with open(RUN_ID_PATH, "r") as f:
        return f.read().strip()


def exact_match_eval(answer, context):
    """Return True if *answer* is found as a substring within *context*."""
    if not answer or not context:
        return False
    return answer in context


def process_row(run_id, query, retrieved_context, generated_answer):
    """Process a single CSV row.

    Creates a LangWatch trace named ``Batch_RAG_{run_id}`` with a nested
    ``Retrieval`` span of type ``rag_retrieval``.  The query is logged as the
    span input and the (truncated) retrieved_context as the span output.  A
    client-side ``exact_match_eval`` evaluation is added to the span.

    Returns ``True`` if the evaluation passed, ``False`` otherwise.
    """
    # Compute the client-side evaluation using the *full* (untruncated)
    # retrieved_context so the evaluation reflects the actual retrieval result.
    passed = exact_match_eval(generated_answer, retrieved_context)
    score = 1.0 if passed else 0.0

    # Truncate retrieved_context before logging to stay under LangWatch's
    # 1 MB body size limit.
    truncated_context = retrieved_context[:MAX_CONTEXT_LENGTH]

    trace_name = f"Batch_RAG_{run_id}"

    try:
        # Create the trace (acts as a context manager).
        with langwatch.trace(name=trace_name) as tr:
            # Create a nested span for the retrieval operation.
            with langwatch.span(
                name="Retrieval",
                type="rag_retrieval",
                input=query,
                output=truncated_context,
            ) as span:
                # Add the client-side custom evaluation to the span.
                span.add_evaluation(
                    name="exact_match_eval",
                    passed=passed,
                    score=score,
                    label="pass" if passed else "fail",
                    details=(
                        "generated_answer found as substring in retrieved_context"
                        if passed
                        else "generated_answer NOT found as substring in retrieved_context"
                    ),
                )
    except Exception as exc:
        # Log the error but don't crash — the evaluation result is still
        # valid because it was computed client-side.
        print(f"  WARNING: LangWatch error for this row: {exc}", file=sys.stderr)

    return passed


def main():
    parser = argparse.ArgumentParser(
        description="Batch process RAG history with LangWatch evaluations"
    )
    parser.add_argument(
        "--input", required=True, help="Input CSV file path"
    )
    parser.add_argument(
        "--output", required=True, help="Output summary JSON file path"
    )
    args = parser.parse_args()

    # Read the run-id from the artifacts file.
    run_id = read_run_id()
    print(f"Run ID: {run_id}")

    # Substitute run-id in the output filename if a template is used.
    output_file = args.output.replace("${run-id}", run_id)

    # Initialize the LangWatch client (uses LANGWATCH_API_KEY from the
    # environment by default).
    langwatch.setup()

    total_processed = 0
    total_passed = 0
    total_failed = 0

    # Process the CSV file.
    with open(args.input, "r", newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            query = row.get("query", "") or ""
            retrieved_context = row.get("retrieved_context", "") or ""
            generated_answer = row.get("generated_answer", "") or ""

            passed = process_row(
                run_id, query, retrieved_context, generated_answer
            )

            total_processed += 1
            if passed:
                total_passed += 1
            else:
                total_failed += 1

            print(f"  Row {total_processed}: {'PASS' if passed else 'FAIL'}")

    # Flush all pending spans to LangWatch before exiting.
    try:
        trace_api.get_tracer_provider().force_flush()
    except Exception as exc:
        print(f"WARNING: Failed to flush spans: {exc}", file=sys.stderr)

    # Write the summary JSON file.
    summary = {
        "total_processed": total_processed,
        "total_passed": total_passed,
        "total_failed": total_failed,
    }

    with open(output_file, "w") as f:
        json.dump(summary, f, indent=2)

    print(
        f"\nProcessed {total_processed} rows: "
        f"{total_passed} passed, {total_failed} failed"
    )
    print(f"Summary written to {output_file}")


if __name__ == "__main__":
    main()