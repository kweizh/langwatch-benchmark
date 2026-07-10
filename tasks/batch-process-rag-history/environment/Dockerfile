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
    pip3 install --break-system-packages pytest-json-ctrf && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

RUN mkdir -p /home/user && chmod 0755 /home/user

RUN mkdir -p /home/user/myproject && \
    cd /home/user/myproject && \
    cat >generate_csv.py <<'EOF'
import csv
with open('rag_history.csv', 'w', newline='') as f:
    writer = csv.writer(f)
    writer.writerow(['query', 'retrieved_context', 'generated_answer'])
    huge_context = 'A' * 131000 + 'The capital of France is Paris.' + 'B' * 1000
    writer.writerow(['What is the capital of France?', huge_context, 'The capital of France is Paris.'])
    writer.writerow(['What is the capital of Spain?', 'Madrid is the capital of Spain.', 'Madrid'])
    writer.writerow(['Who wrote Hamlet?', 'Tolkien wrote Lord of the Rings.', 'Tolkien'])
EOF

RUN cd /home/user/myproject && \
    python3 generate_csv.py && \
    rm generate_csv.py

LABEL Author="generate-harbor-tasks"
LABEL Description="LangWatch RAG batch processing task environment with uv installed."

CMD ["/bin/bash", "-c", "trap : TERM INT; sleep infinity & wait"]

# Container contents:
#   - always required apt packages: curl wget ca-certificates git python3 python3-pip python3-pytest bash ripgrep
#   - always required pip3 packages: pytest-json-ctrf
#   - uv binary installed via curl
#   - /home/user/myproject: project directory
#   - /home/user/myproject/rag_history.csv: generated CSV with large fields

# Setup entrypoint script
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh
ENTRYPOINT ["/entrypoint.sh"]
