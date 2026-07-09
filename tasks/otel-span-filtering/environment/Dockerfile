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

# Seed the pre-existing project: a service that already has a global
# OpenTelemetry TracerProvider and an observability module to be implemented.
RUN mkdir -p /home/user/project

RUN cat >/home/user/project/observability.py <<'EOF'
"""Observability integration module.

Implement the two functions below so that LangWatch is integrated alongside the
application's existing global OpenTelemetry TracerProvider, while internal
health-check and database spans are excluded from being exported to LangWatch.
"""


def configure_langwatch(tracer_provider):
    """Attach LangWatch to the already-existing ``tracer_provider``.

    Must not create a new provider or remove the provider's existing span
    processors. Configure LangWatch's export filtering so that spans named
    exactly ``GET /health_check`` and spans whose name starts with ``db.`` are
    excluded from export to LangWatch, while all other spans are exported.
    """
    raise NotImplementedError("configure_langwatch must be implemented")


def run_pipeline(query):
    """Run a small RAG-style pipeline and return a non-empty answer string.

    Emit spans through the global OpenTelemetry tracer, nested under a root span
    named ``rag_pipeline``: ``GET /health_check``, ``db.query.documents``,
    ``rag.retrieve`` and ``llm.generate``.
    """
    raise NotImplementedError("run_pipeline must be implemented")
EOF

RUN cat >/home/user/project/main.py <<'EOF'
"""CLI entrypoint for the observability-instrumented pipeline.

The application already owns a global OpenTelemetry TracerProvider (the team's
existing tracing setup). This entrypoint wires LangWatch onto it and runs the
pipeline for a single query.
"""
import sys

from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import ConsoleSpanExporter, SimpleSpanProcessor

import observability


def build_global_provider():
    provider = TracerProvider()
    # Existing observability backend (console exporter for local development).
    provider.add_span_processor(SimpleSpanProcessor(ConsoleSpanExporter()))
    trace.set_tracer_provider(provider)
    return provider


def main():
    query = sys.argv[1] if len(sys.argv) > 1 else "Hello"
    provider = build_global_provider()
    observability.configure_langwatch(provider)
    answer = observability.run_pipeline(query)
    print(f"Answer: {answer}")
    provider.force_flush()


if __name__ == "__main__":
    main()
EOF

RUN cat >/home/user/project/README.md <<'EOF'
# LangWatch OpenTelemetry Span Filtering

This service already configures a global OpenTelemetry TracerProvider. Implement
`observability.py` to integrate LangWatch alongside it, excluding internal
health-check and database spans from export to LangWatch.

Run: `python main.py "<query>"`
EOF

# Install LangWatch + OpenTelemetry into a uv-managed virtualenv (per project
# guidance) and put it on PATH so the SDK is importable by default.
RUN cd /home/user/project && \
    uv venv && \
    . .venv/bin/activate && \
    uv pip install \
        langwatch \
        opentelemetry-sdk \
        opentelemetry-exporter-otlp-proto-http \
        pytest \
        pytest-json-ctrf

ENV PATH="/home/user/project/.venv/bin:${PATH}"

LABEL Author="generate-harbor-tasks"
LABEL Description="LangWatch + OpenTelemetry span-filtering task: integrate LangWatch alongside an existing global TracerProvider and exclude health-check/db spans."

CMD ["/bin/bash", "-c", "trap : TERM INT; sleep infinity & wait"]

# Container contents:
#   - always required apt packages: curl wget ca-certificates git python3 python3-pip python3-pytest bash ripgrep
#   - always required pip3 packages: pytest-json-ctrf
#   - uv-managed virtualenv at /home/user/project/.venv (on PATH) with:
#       langwatch, opentelemetry-sdk, opentelemetry-exporter-otlp-proto-http, pytest, pytest-json-ctrf
#   - /home/user/project: pre-existing service with a global OpenTelemetry setup
#       - observability.py: stub module for the agent to implement
#       - main.py: CLI that builds the global provider and runs the pipeline
#       - README.md: task overview

# Setup entrypoint script
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh
ENTRYPOINT ["/entrypoint.sh"]
