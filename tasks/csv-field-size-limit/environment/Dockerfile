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

# Pre-provision the LangWatch project with a uv-managed virtual environment.
# LangWatch (and its pandas-backed dataset support) MUST be installed via uv,
# not system pip, to avoid the pluggy/RECORD uninstall errors documented in the
# research plan.
RUN mkdir -p /home/user/langwatch-csv-pipeline && \
    cd /home/user/langwatch-csv-pipeline && \
    uv venv --python python3 /home/user/langwatch-csv-pipeline/.venv && \
    uv pip install --python /home/user/langwatch-csv-pipeline/.venv/bin/python \
        langwatch pandas

LABEL Author="generate-harbor-tasks"
LABEL Description="LangWatch CSV round-trip pipeline task: uv venv with langwatch + pandas preinstalled at /home/user/langwatch-csv-pipeline."

CMD ["/bin/bash", "-c", "trap : TERM INT; sleep infinity & wait"]

# Container contents:
#   - always required apt packages: curl wget ca-certificates git python3 python3-pip python3-pytest bash ripgrep
#   - always required pip3 packages: pytest-json-ctrf
#   - uv installed to /usr/local/bin/uv for LangWatch package management
#   - /home/user/langwatch-csv-pipeline: task project directory
#   - /home/user/langwatch-csv-pipeline/.venv: uv venv with langwatch + pandas preinstalled
#   - Verification (test_final_state.py) uses only the Python standard library and
#     drives the pipeline via the venv interpreter through subprocess.

# Setup entrypoint script
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh
ENTRYPOINT ["/entrypoint.sh"]
