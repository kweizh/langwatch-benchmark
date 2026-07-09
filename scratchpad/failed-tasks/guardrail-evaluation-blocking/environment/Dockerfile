FROM ubuntu:24.04

ARG POCHI_VERSION

RUN apt-get update -y && \
    DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
        curl wget ca-certificates git python3 python3-pip python3-pytest python3-dev build-essential bash ripgrep && \
    ln -s /usr/bin/python3 /usr/bin/python && \
    curl -fsSL https://getpochi.com/install.sh | bash -s ${POCHI_VERSION} && \
    ln -s /root/.pochi/bin/pochi /usr/local/bin/pochi && \
    curl -LsSf https://astral.sh/uv/install.sh | sh && \
    ln -s /root/.local/bin/uv /usr/local/bin/uv && \
    ln -s /root/.local/bin/uvx /usr/local/bin/uvx && \
    uv pip install --system --break-system-packages \
        langwatch opentelemetry-proto pytest-json-ctrf && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

RUN mkdir -p /home/user && chmod 0755 /home/user
RUN mkdir -p /home/user/project

LABEL Author="generate-harbor-tasks"
LABEL Description="LangWatch Python environment for a blocking PII guardrail task; langwatch + opentelemetry-proto pre-installed system-wide, uv available."

CMD ["/bin/bash", "-c", "trap : TERM INT; sleep infinity & wait"]

# Container contents:
#   - always required apt packages: curl wget ca-certificates git python3 python3-pip python3-pytest bash ripgrep
#   - build tooling (python3-dev build-essential) for any native wheels pulled in by langwatch deps
#   - always required pip3 packages: pytest-json-ctrf
#   - uv installed and symlinked to /usr/local/bin/uv (required to install langwatch packages)
#   - langwatch + opentelemetry-proto installed system-wide so the agent CLI and the verifier's
#     in-process OTLP collector can both import them
#   - /home/user/project: empty project directory where the agent implements agent.py and main.py

# Setup entrypoint script
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh
ENTRYPOINT ["/entrypoint.sh"]
