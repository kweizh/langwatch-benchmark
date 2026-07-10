FROM ubuntu:24.04

ARG POCHI_VERSION

RUN apt-get update -y && \
    DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
        curl wget ca-certificates git python3 python3-pip python3-pytest bash ripgrep && \
    ln -s /usr/bin/python3 /usr/bin/python && \
    curl -fsSL https://getpochi.com/install.sh | bash -s ${POCHI_VERSION} && \
    ln -s /root/.pochi/bin/pochi /usr/local/bin/pochi && \
    pip3 install --break-system-packages pytest-json-ctrf langwatch requests && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

RUN mkdir -p /home/user && chmod 0755 /home/user

RUN mkdir -p /home/user/myproject && \
    cd /home/user/myproject && \
    cat >mock_collector.py <<'EOF'
from http.server import BaseHTTPRequestHandler, HTTPServer

class MockCollector(BaseHTTPRequestHandler):
    def do_POST(self):
        content_length = int(self.headers.get('Content-Length', 0))
        post_data = self.rfile.read(content_length)
        with open('/home/user/myproject/payload.json', 'w') as f:
            f.write(post_data.decode('utf-8'))
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b'{"status":"ok"}')

    def do_GET(self):
        if self.path == '/health':
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b'{"status":"ok"}')

if __name__ == '__main__':
    server = HTTPServer(('localhost', 8080), MockCollector)
    server.serve_forever()
EOF

RUN cd /home/user/myproject && \
    cat >run.py <<'EOF'
import langwatch
import os
import time

langwatch.setup(
    api_key=os.getenv("LANGWATCH_API_KEY", "dummy_key"),
    endpoint=os.getenv("LANGWATCH_ENDPOINT", "http://localhost:8080")
)

@langwatch.trace(name="RAG Pipeline")
def run_rag_pipeline(question: str):
    answer = "The capital of France is Paris."
    retrieved_context = "A" * 2000000  # 2MB document

    with langwatch.span(name="Document Retrieval", type="rag_retrieval") as span:
        span.update(
            input={"query": question},
            output={"documents": [retrieved_context]}
        )
    return answer

if __name__ == "__main__":
    run_rag_pipeline("What is the capital of France?")
    # allow time for background telemetry to flush
    time.sleep(2)
EOF

LABEL Author="generate-harbor-tasks"
LABEL Description="LangWatch task environment for client-side payload filtering."

CMD ["/bin/bash", "-c", "trap : TERM INT; sleep infinity & wait"]

# Container contents:
#   - always required apt packages: curl wget ca-certificates git python3 python3-pip python3-pytest bash ripgrep
#   - always required pip3 packages: pytest-json-ctrf
#   - langwatch and requests installed via pip3
#   - /home/user/myproject: project directory
#   - /home/user/myproject/mock_collector.py: mock LangWatch API
#   - /home/user/myproject/run.py: initial script to modify

# Setup entrypoint script
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh
ENTRYPOINT ["/entrypoint.sh"]
