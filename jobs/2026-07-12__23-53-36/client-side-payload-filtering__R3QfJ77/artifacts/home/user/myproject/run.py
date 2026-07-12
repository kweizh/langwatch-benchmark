import langwatch
import os
import time

langwatch.setup(
    api_key=os.getenv("LANGWATCH_API_KEY", "dummy_key"),
    endpoint_url=os.getenv("LANGWATCH_ENDPOINT", "http://localhost:8080")
)

@langwatch.trace(name="RAG Pipeline")
def run_rag_pipeline(question: str):
    answer = "The capital of France is Paris."
    retrieved_context = "A" * 2000000  # 2MB document

    # Client-side payload filtering: truncate the large document to avoid
    # exceeding the collector's 1MB body size limit.
    max_doc_chars = 1000
    truncated_context = retrieved_context[:max_doc_chars]

    with langwatch.span(name="Document Retrieval", type="rag_retrieval") as span:
        span.update(
            input={"query": question},
            output={"documents": [truncated_context]}
        )
    return answer

if __name__ == "__main__":
    run_rag_pipeline("What is the capital of France?")
    # allow time for background telemetry to flush
    time.sleep(2)
