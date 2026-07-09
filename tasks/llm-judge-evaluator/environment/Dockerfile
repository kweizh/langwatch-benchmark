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

# Seed the pre-existing project: a QA pipeline skeleton that the agent must
# implement so it runs the built-in LangWatch LLM-as-a-Judge Boolean evaluator
# on its produced answer with a custom rubric and attaches the returned verdict
# to the answer-generation span of the trace.
RUN mkdir -p /home/user/project

RUN cat >/home/user/project/qa_pipeline.py <<'EOF'
"""QA pipeline with a built-in LangWatch LLM-as-a-Judge evaluation.

Implement the callables below so that:
  * ``retrieve`` deterministically returns context passages for a question,
  * ``run_pipeline`` runs the pipeline under a LangWatch trace (emitting spans
    ``qa_pipeline`` -> ``retrieve_context`` / ``generate_answer``), invokes the
    built-in LLM-as-a-Judge Boolean evaluator (slug ``langevals/llm_boolean``)
    on the produced answer while ``generate_answer`` is the active span, and
    records the returned verdict both on the trace and in ``judge_result.json``.

The evaluator must receive ``input`` (the question), ``output`` (your answer)
and ``contexts`` (the retrieved passages) as data, and a custom rubric via the
evaluator settings. Use the evaluation name ``answer-quality-judge``.

Read the LangWatch API key and endpoint from the environment
(``LANGWATCH_API_KEY`` and ``LANGWATCH_ENDPOINT``). Do not hardcode credentials.
"""


def retrieve(question):
    """Deterministically retrieve context passages for ``question``.

    Returns a non-empty list of strings drawn from a fixed in-code corpus.
    Must be a pure function of the question and corpus (no randomness, no network).
    """
    raise NotImplementedError("retrieve must be implemented")


def run_pipeline(question):
    """Run the end-to-end QA pipeline and return a result dict.

    Emit spans ``qa_pipeline`` (root), ``retrieve_context`` and
    ``generate_answer``; while ``generate_answer`` is the active span, run the
    built-in LLM-as-a-Judge Boolean evaluator with a custom rubric, capture the
    returned verdict, write it to ``judge_result.json`` and return
    ``{"answer": <str>, "judgement": {"passed": bool, "score": number,
    "label": str, "details": str}}``.
    """
    raise NotImplementedError("run_pipeline must be implemented")
EOF

RUN cat >/home/user/project/main.py <<'EOF'
"""CLI entrypoint for the QA + LLM-as-a-Judge pipeline.

Runs the pipeline for a single question and prints the answer plus the judge
verdict returned by the LangWatch built-in evaluator.
"""
import sys

import qa_pipeline


def main():
    question = (
        sys.argv[1]
        if len(sys.argv) > 1
        else "How do I attach an evaluation to a LangWatch trace?"
    )
    result = qa_pipeline.run_pipeline(question)
    judgement = result["judgement"]
    print(f"Answer: {result['answer']}")
    print(
        f"Judgement: {judgement['passed']} {judgement['score']} {judgement['label']}"
    )


if __name__ == "__main__":
    main()
EOF

RUN cat >/home/user/project/README.md <<'EOF'
# LangWatch LLM-as-a-Judge Evaluator

Implement `qa_pipeline.py` so the QA pipeline runs LangWatch's built-in
LLM-as-a-Judge Boolean evaluator (`langevals/llm_boolean`) on its produced
answer with a custom rubric, and attaches the returned verdict to the
`generate_answer` span of the trace while also writing it to `judge_result.json`.

Run: `python main.py "<question>"`
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
LABEL Description="LangWatch LLM-as-a-Judge task: implement a QA pipeline that runs the built-in langevals/llm_boolean evaluator with a custom rubric and attaches the verdict to the answer span."

# Container contents:
#   - always required apt packages: curl wget ca-certificates git python3 python3-pip python3-pytest bash ripgrep
#   - always required pip3 packages: pytest-json-ctrf
#   - uv-managed virtualenv at /home/user/project/.venv (on PATH) with:
#       langwatch, opentelemetry-sdk, opentelemetry-exporter-otlp-proto-http,
#       opentelemetry-proto, pytest, pytest-json-ctrf
#   - /home/user/project: pre-existing QA pipeline skeleton
#       - qa_pipeline.py: stub module for the agent to implement (retrieve, run_pipeline)
#       - main.py: CLI that prints the answer and judge verdict
#       - README.md: task overview

CMD ["/bin/bash", "-c", "trap : TERM INT; sleep infinity & wait"]

# Setup entrypoint script
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh
ENTRYPOINT ["/entrypoint.sh"]
