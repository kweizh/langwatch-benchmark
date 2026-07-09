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

# Seed the project: a RAG assistant that needs an offline batch evaluation loop.
RUN mkdir -p /home/user/project/data

# Retrieval corpus for the RAG pipeline.
RUN cat >/home/user/project/data/knowledge_base.json <<'EOF'
[
  {
    "id": "kb-init",
    "title": "Initializing a batch evaluation run",
    "content": "In the LangWatch Python SDK you start a server-side offline batch evaluation by initializing an evaluation run with a descriptive name, then looping over your dataset so every row is tracked as part of the run."
  },
  {
    "id": "kb-apikey",
    "title": "Authentication configuration",
    "content": "The LangWatch SDK reads credentials from the environment. The LANGWATCH_API_KEY environment variable holds the API key, LANGWATCH_ENDPOINT points at the backend, and LANGWATCH_PROJECT_ID is required for service-scoped keys."
  },
  {
    "id": "kb-ragas",
    "title": "RAG quality evaluators",
    "content": "LangWatch ships built-in RAGAS evaluators that run on the backend. The context-utilization evaluator measures how well the generated answer makes use of the retrieved contexts, and is referenced by the slug legacy/ragas_context_utilization."
  },
  {
    "id": "kb-otel",
    "title": "OpenTelemetry export",
    "content": "LangWatch is OpenTelemetry-native and exports telemetry as OTLP traces over HTTP to the configured endpoint, so it integrates with any OpenTelemetry compatible pipeline without vendor lock-in."
  },
  {
    "id": "kb-uv",
    "title": "Installing the SDK",
    "content": "LangWatch Python packages should be installed with the uv package manager inside a virtual environment, because some dependencies are not compatible with the system pip on the underlying operating system."
  },
  {
    "id": "kb-prompts",
    "title": "Prompt management",
    "content": "The prompts API lets you fetch a versioned prompt by handle and compile it with dynamic template variables, producing ready-to-use chat messages for your model call."
  },
  {
    "id": "kb-loop",
    "title": "Iterating datasets",
    "content": "Wrapping your dataset iterator with the evaluation loop primitive keeps every entry tracked and lets you run built-in evaluators and log custom metrics for each row, optionally in parallel across threads."
  },
  {
    "id": "kb-contexts",
    "title": "Structuring evaluator data",
    "content": "Built-in evaluators receive a data object containing the input question, the produced output answer, and the retrieved contexts as a list, so the metric can compare the answer against each individual retrieved chunk."
  }
]
EOF

# Evaluation dataset: one question per row to run through the RAG pipeline.
RUN cat >/home/user/project/data/qa_dataset.csv <<'EOF'
id,question
q1,How do I initialize a batch evaluation run in the LangWatch Python SDK?
q2,Which environment variable holds the LangWatch API key?
q3,Which built-in evaluator measures how well an answer uses the retrieved contexts?
q4,How does LangWatch export telemetry data?
q5,Which package manager should be used to install LangWatch Python packages?
q6,How can prompts be fetched and compiled with the LangWatch SDK?
EOF

RUN cat >/home/user/project/run_evaluation.py <<'EOF'
"""Offline batch RAG evaluation entrypoint.

Implement this script so that running `python run_evaluation.py`:
  - reads LANGWATCH_API_KEY / LANGWATCH_ENDPOINT / LANGWATCH_PROJECT_ID from the env,
  - loads data/qa_dataset.csv and data/knowledge_base.json,
  - initializes a LangWatch batch evaluation run (name must include the run-id
    read from /logs/artifacts/run-id),
  - loops over every dataset row, runs a real RAG pipeline (retrieve + generate),
  - invokes the built-in evaluator `legacy/ragas_context_utilization` on the
    LangWatch backend with data={"input", "output", "contexts"} for each row,
  - writes eval_summary.json and prints a `Rows evaluated: <N>` line.
"""


def main():
    raise NotImplementedError("run_evaluation.py must be implemented")


if __name__ == "__main__":
    main()
EOF

RUN cat >/home/user/project/README.md <<'EOF'
# LangWatch Offline Batch RAG Evaluation

Implement `run_evaluation.py` to run an offline, dataset-driven batch evaluation
of a RAG pipeline using LangWatch's SDK-driven evaluation API and the built-in
`legacy/ragas_context_utilization` evaluator.

- Dataset: `data/qa_dataset.csv`
- Retrieval corpus: `data/knowledge_base.json`
- Run: `python run_evaluation.py`
EOF

# Install LangWatch into a uv-managed virtualenv (per project guidance) and put
# it on PATH so the SDK is importable and used by pytest during verification.
RUN cd /home/user/project && \
    uv venv && \
    . .venv/bin/activate && \
    uv pip install \
        langwatch \
        pandas \
        pytest \
        pytest-json-ctrf

ENV PATH="/home/user/project/.venv/bin:${PATH}"

LABEL Author="generate-harbor-tasks"
LABEL Description="LangWatch offline batch RAG evaluation task: drive a dataset through a RAG pipeline and score each row with the built-in legacy/ragas_context_utilization evaluator."

CMD ["/bin/bash", "-c", "trap : TERM INT; sleep infinity & wait"]

# Container contents:
#   - always required apt packages: curl wget ca-certificates git python3 python3-pip python3-pytest bash ripgrep
#   - always required pip3 packages: pytest-json-ctrf
#   - uv-managed virtualenv at /home/user/project/.venv (on PATH) with:
#       langwatch, pandas, pytest, pytest-json-ctrf
#   - /home/user/project: RAG assistant project
#       - data/qa_dataset.csv: evaluation dataset (one question per row)
#       - data/knowledge_base.json: retrieval corpus for the RAG pipeline
#       - run_evaluation.py: stub batch-evaluation script for the agent to implement
#       - README.md: task overview

# Setup entrypoint script
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh
ENTRYPOINT ["/entrypoint.sh"]
