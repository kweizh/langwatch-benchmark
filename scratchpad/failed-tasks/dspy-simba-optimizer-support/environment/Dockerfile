FROM ubuntu:24.04

ARG POCHI_VERSION

# Base tooling + Pochi CLI + uv (used to manage the langwatch/dspy virtualenv).
RUN apt-get update -y && \
    DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
        curl wget ca-certificates git python3 python3-pip python3-pytest bash ripgrep \
        python3-venv build-essential && \
    ln -s /usr/bin/python3 /usr/bin/python && \
    curl -fsSL https://getpochi.com/install.sh | bash -s ${POCHI_VERSION} && \
    ln -s /root/.pochi/bin/pochi /usr/local/bin/pochi && \
    pip3 install --break-system-packages pytest-json-ctrf && \
    curl -LsSf https://astral.sh/uv/install.sh | sh && \
    ln -s /root/.local/bin/uv /usr/local/bin/uv && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

RUN mkdir -p /home/user && chmod 0755 /home/user

# Create the project and install langwatch + dspy into a uv-managed virtualenv.
# uv is REQUIRED for these packages (installing langwatch-family packages with
# plain pip can fail with "Cannot uninstall pluggy ... RECORD file not found").
RUN mkdir -p /home/user/project && \
    cd /home/user/project && \
    uv venv /home/user/project/.venv --python python3 && \
    uv pip install --python /home/user/project/.venv/bin/python \
        "langwatch==0.26.0" "dspy==3.2.1" && \
    /home/user/project/.venv/bin/python -c "import langwatch, langwatch.dspy, dspy; from dspy.teleprompt import SIMBA; print('deps-ok')"

# A short pointer for the agent; the solution files (simba_support.py, run.py)
# are created by the task executor.
RUN cat > /home/user/project/README.md <<'EOF'
# LangWatch DSPy visualizer: SIMBA support

Dependencies (`langwatch`, `dspy`) are preinstalled in the uv-managed
virtualenv at `/home/user/project/.venv`. Run everything with:

    /home/user/project/.venv/bin/python <script>

See the task instructions for what to build (a `simba_support.py` module and a
`run.py` CLI). `langwatch.dspy` reads `LANGWATCH_ENDPOINT` and
`LANGWATCH_API_KEY` from the environment.
EOF

LABEL Author="generate-harbor-tasks"
LABEL Description="LangWatch + DSPy (SIMBA) task environment with a uv-managed venv at /home/user/project/.venv."

CMD ["/bin/bash", "-c", "trap : TERM INT; sleep infinity & wait"]

# Container contents:
#   - always required apt packages: curl wget ca-certificates git python3 python3-pip python3-pytest bash ripgrep
#   - always required pip3 packages: pytest-json-ctrf
#   - uv installed and symlinked to /usr/local/bin/uv
#   - /home/user/project: task project directory
#   - /home/user/project/.venv: uv-managed virtualenv with langwatch==0.26.0 and dspy==3.2.1
#   - /home/user/project/README.md: pointer note for the task executor

# Setup entrypoint script
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh
ENTRYPOINT ["/entrypoint.sh"]
