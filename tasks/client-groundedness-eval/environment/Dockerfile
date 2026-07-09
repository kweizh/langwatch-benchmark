FROM ubuntu:24.04

ARG POCHI_VERSION

RUN apt-get update -y && \
    DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
        curl wget ca-certificates git python3 python3-pip python3-pytest bash ripgrep && \
    ln -s /usr/bin/python3 /usr/bin/python && \
    curl -fsSL https://getpochi.com/install.sh | bash -s ${POCHI_VERSION} && \
    ln -s /root/.pochi/bin/pochi /usr/local/bin/pochi && \
    pip3 install --break-system-packages pytest-json-ctrf && \
    curl -LsSf https://astral.sh/uv/install.sh | sh && \
    ln -s /root/.local/bin/uv /usr/local/bin/uv && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

RUN mkdir -p /home/user && chmod 0755 /home/user

# Seed the pre-existing project: a RAG pipeline skeleton that the agent must
# implement so it logs a custom client-side groundedness evaluation onto the
# answer-generation span with langwatch.get_current_span().add_evaluation(...).
RUN mkdir -p /home/user/project

RUN cat >/home/user/project/pipeline.py <<'EOF'
"""RAG pipeline with a custom client-side groundedness evaluation.

Implement the three callables below so that:
  * ``retrieve`` deterministically returns context passages for a query,
  * ``compute_groundedness`` scores an answer against retrieved contexts using
    the metric described in the task, and
  * ``run_pipeline`` runs the pipeline under a LangWatch trace (emitting spans
    ``rag_pipeline`` -> ``retrieve_context`` / ``generate_answer``) and logs the
    groundedness result as a custom evaluation named ``groundedness`` on the
    ``generate_answer`` span via ``langwatch.get_current_span().add_evaluation``.

Read the LangWatch API key and endpoint from the environment
(``LANGWATCH_API_KEY`` and ``LANGWATCH_ENDPOINT``). Do not hardcode credentials.
"""


def retrieve(query):
    """Deterministically retrieve context passages for ``query``.

    Returns a non-empty list of strings drawn from a fixed in-code corpus.
    Must be a pure function of the query and corpus (no randomness, no network).
    """
    raise NotImplementedError("retrieve must be implemented")


def compute_groundedness(answer, contexts):
    """Compute groundedness of ``answer`` against ``contexts``.

    Returns a dict with keys ``score`` (float), ``passed`` (bool), ``label``
    (str) and ``details`` (str), following the metric specification in the task.
    """
    raise NotImplementedError("compute_groundedness must be implemented")


def run_pipeline(query):
    """Run the end-to-end RAG pipeline and return the answer string.

    Emit spans ``rag_pipeline`` (root), ``retrieve_context`` and
    ``generate_answer``; while ``generate_answer`` is the current span, log the
    groundedness evaluation via
    ``langwatch.get_current_span().add_evaluation(name="groundedness", ...)``.
    """
    raise NotImplementedError("run_pipeline must be implemented")
EOF

RUN cat >/home/user/project/main.py <<'EOF'
"""CLI entrypoint for the RAG groundedness pipeline.

Runs the pipeline for a single query and prints the answer plus the computed
groundedness score and label.
"""
import sys

import pipeline


def main():
    query = sys.argv[1] if len(sys.argv) > 1 else "What is LangWatch observability?"
    contexts = pipeline.retrieve(query)
    answer = pipeline.run_pipeline(query)
    result = pipeline.compute_groundedness(answer, contexts)
    print(f"Answer: {answer}")
    print(f"Groundedness: {result['score']} {result['label']}")


if __name__ == "__main__":
    main()
EOF

RUN cat >/home/user/project/README.md <<'EOF'
# LangWatch Client-Side Groundedness Evaluation

Implement `pipeline.py` so the RAG pipeline computes a custom groundedness score
for its answer and logs it onto the `generate_answer` span using
`langwatch.get_current_span().add_evaluation(...)`.

Run: `python main.py "<query>"`
EOF

# Install LangWatch + OpenTelemetry (SDK, OTLP/HTTP exporter, proto) into a
# uv-managed virtualenv (per project guidance) and put it on PATH so the SDK is
# importable by default and the verifier can decode OTLP exports.
RUN cd /home/user/project && \
    uv venv && \
    . .venv/bin/activate && \
    uv pip install \
        langwatch \
        opentelemetry-sdk \
        opentelemetry-exporter-otlp-proto-http \
        opentelemetry-proto \
        pytest \
        pytest-json-ctrf

ENV PATH="/home/user/project/.venv/bin:${PATH}"

LABEL Author="generate-harbor-tasks"
LABEL Description="LangWatch client-side groundedness evaluation task: implement a RAG pipeline that computes a deterministic groundedness score and logs it via span.add_evaluation on the answer span."

CMD ["/bin/bash", "-c", "trap : TERM INT; sleep infinity & wait"]

# Container contents:
#   - always required apt packages: curl wget ca-certificates git python3 python3-pip python3-pytest bash ripgrep
#   - always required pip3 packages: pytest-json-ctrf
#   - uv-managed virtualenv at /home/user/project/.venv (on PATH) with:
#       langwatch, opentelemetry-sdk, opentelemetry-exporter-otlp-proto-http,
#       opentelemetry-proto, pytest, pytest-json-ctrf
#   - /home/user/project: pre-existing RAG pipeline skeleton
#       - pipeline.py: stub module for the agent to implement (retrieve,
#         compute_groundedness, run_pipeline)
#       - main.py: CLI that prints the answer and groundedness score/label
#       - README.md: task overview

# Setup entrypoint script
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh
ENTRYPOINT ["/entrypoint.sh"]
