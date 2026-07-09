FROM ubuntu:24.04

ARG POCHI_VERSION

RUN apt-get update -y && \
    DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
        curl wget ca-certificates git python3 python3-pip python3-pytest bash ripgrep && \
    ln -s /usr/bin/python3 /usr/bin/python && \
    curl -fsSL https://getpochi.com/install.sh | bash -s ${POCHI_VERSION} && \
    ln -s /root/.pochi/bin/pochi /usr/local/bin/pochi && \
    curl -LsSf https://astral.sh/uv/install.sh | sh && \
    ln -s /root/.local/bin/uv /usr/local/bin/uv && \
    ln -s /root/.local/bin/uvx /usr/local/bin/uvx && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# Isolated verifier virtualenv (created with uv) that owns pytest and the LangWatch
# SDK used by the verifier. It is independent of any venv the agent creates under the
# project directory, so the agent cannot break the verifier's toolchain.
RUN uv venv /opt/verifier-venv && \
    uv pip install --python /opt/verifier-venv/bin/python \
        pytest pytest-json-ctrf requests \
        langwatch opentelemetry-exporter-otlp-proto-http

ENV PATH="/opt/verifier-venv/bin:${PATH}"

RUN mkdir -p /home/user && chmod 0755 /home/user

# Project skeleton with an oversized RAG corpus (> 1MB of raw content). Each document
# carries a HEAD_CANARY_<i> token near the start and a TAIL_CANARY_<i> token at the very
# end so the verifier can confirm heads are retained and tails are truncated away.
RUN mkdir -p /home/user/project/data && \
    python3 - <<'PY'
import json

docs = []
for i in range(5):
    filler = "lorem ipsum dolor sit amet " * 12000  # ~324 KB per document
    content = f"HEAD_CANARY_{i} " + filler + f" TAIL_CANARY_{i}"
    docs.append({
        "document_id": f"doc-{i}",
        "chunk_id": f"chunk-{i}-0",
        "content": content,
    })

with open("/home/user/project/data/documents.json", "w", encoding="utf-8") as f:
    json.dump(docs, f)
PY

LABEL Author="generate-harbor-tasks"
LABEL Description="LangWatch Python SDK task: client-side RAG payload truncation to stay under the 1MB collector limit, with an isolated uv verifier venv and an oversized canary corpus."

CMD ["/bin/bash", "-c", "trap : TERM INT; sleep infinity & wait"]

# Container contents:
#   - always required apt packages: curl wget ca-certificates git python3 python3-pip python3-pytest bash ripgrep
#   - always required pip3 packages: pytest-json-ctrf (installed into the verifier venv)
#   - uv package manager (symlinked into /usr/local/bin) for installing LangWatch packages
#   - /opt/verifier-venv: isolated verifier venv with pytest, pytest-json-ctrf, langwatch,
#     and the OTLP/HTTP proto exporter (provides opentelemetry.proto for decoding exports)
#   - /home/user/project: project root the agent works in
#   - /home/user/project/data/documents.json: oversized RAG corpus (>1MB) with HEAD/TAIL canary tokens

# Setup entrypoint script
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh
ENTRYPOINT ["/entrypoint.sh"]
