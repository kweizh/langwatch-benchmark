FROM ubuntu:24.04

ARG POCHI_VERSION

RUN apt-get update -y && \
    DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
        curl wget ca-certificates git python3 python3-pip python3-pytest bash ripgrep && \
    ln -s /usr/bin/python3 /usr/bin/python && \
    curl -fsSL https://getpochi.com/install.sh | bash -s ${POCHI_VERSION} && \
    ln -s /root/.pochi/bin/pochi /usr/local/bin/pochi && \
    pip3 install --break-system-packages pytest-json-ctrf uv && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

RUN mkdir -p /home/user && chmod 0755 /home/user

RUN mkdir -p /home/user/myproject && \
    cd /home/user/myproject && \
    uv venv && \
    . .venv/bin/activate && \
    uv pip install langwatch dspy-ai && \
    cat >optimize.py <<'EOF'
import dspy
import langwatch
import os

# Use dummy keys for offline tracking
os.environ["LANGWATCH_API_KEY"] = "dummy"
os.environ["LANGWATCH_ENDPOINT"] = "http://localhost:9999"

langwatch.setup()
langwatch.dspy.init()

dspy.settings.configure(lm=dspy.DummyLM([{"answer": "foo"}]))

class BasicQA(dspy.Signature):
    question = dspy.InputField()
    answer = dspy.OutputField()

class MyModule(dspy.Module):
    def __init__(self):
        super().__init__()
        self.prog = dspy.Predict(BasicQA)
    def forward(self, question):
        return self.prog(question=question)

trainset = [dspy.Example(question="What is 1+1?", answer="2").with_inputs("question")]

# The crash happens when we initialize the optimizer
from dspy.teleprompt import SIMBA

optimizer = SIMBA()

print("Optimization completed successfully")
EOF

LABEL Author="generate-harbor-tasks"
LABEL Description="LangWatch DSPy tracking task environment with python venv and optimize.py script."

CMD ["/bin/bash", "-c", "trap : TERM INT; sleep infinity & wait"]

# Container contents:
#   - always required apt packages: curl wget ca-certificates git python3 python3-pip python3-pytest bash ripgrep
#   - always required pip3 packages: pytest-json-ctrf uv
#   - /home/user/myproject: project directory
#   - /home/user/myproject/.venv: python virtual environment with langwatch and dspy-ai
#   - /home/user/myproject/optimize.py: initial script using unsupported SIMBA optimizer

# Setup entrypoint script
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh
ENTRYPOINT ["/entrypoint.sh"]
