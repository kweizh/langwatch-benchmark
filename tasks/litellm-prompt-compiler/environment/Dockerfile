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
    pip3 install --break-system-packages pytest-json-ctrf pyyaml && \
    uv pip install --system --break-system-packages langwatch litellm pyyaml && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

RUN mkdir -p /home/user && chmod 0755 /home/user

# Provision the pre-existing LangWatch prompts project (initial state):
# a versioned, locally materialized prompt for the handle "support-triage-agent".
RUN mkdir -p /home/user/myproject/prompts/.materialized && \
    cat >/home/user/myproject/prompts.json <<'EOF'
{
  "prompts": {
    "support-triage-agent": "2"
  }
}
EOF

RUN cat >/home/user/myproject/prompts-lock.json <<'EOF'
{
  "lockfileVersion": 1,
  "prompts": {
    "support-triage-agent": {
      "version": 2,
      "versionId": "prompt_version_zlt_seed_0002",
      "materialized": "prompts/.materialized/support-triage-agent.prompt.yaml"
    }
  }
}
EOF

RUN cat >/home/user/myproject/prompts/.materialized/support-triage-agent.prompt.yaml <<'EOF'
model: openai/gpt-4o-mini
modelParameters:
  temperature: 0.3
messages:
  - role: system
    content: |
      You are a support triage agent handling a {{account_tier}} tier customer.
      Assign an internal priority of {{priority}} and keep your tone professional.
  - role: user
    content: |
      Customer {{customer_name}} has reported the following issue:
      {{issue_summary}}
EOF

LABEL Author="generate-harbor-tasks"
LABEL Description="LangWatch + LiteLLM prompt-compiler task: a pre-provisioned, locally materialized versioned prompt in /home/user/myproject, with langwatch and litellm installed via uv."

CMD ["/bin/bash", "-c", "trap : TERM INT; sleep infinity & wait"]

# Container contents:
#   - always required apt packages: curl wget ca-certificates git python3 python3-pip python3-pytest bash ripgrep
#   - always required pip3 packages: pytest-json-ctrf (plus pyyaml for the verifier tests)
#   - uv installed and used to install the langwatch and litellm Python SDKs into the system interpreter
#   - /home/user/myproject: pre-provisioned LangWatch prompts project
#       - prompts.json / prompts-lock.json: dependency + lock files resolving "support-triage-agent" to version 2
#       - prompts/.materialized/support-triage-agent.prompt.yaml: materialized versioned prompt
#         (model openai/gpt-4o-mini; system + user messages referencing {{customer_name}}, {{account_tier}}, {{issue_summary}}, {{priority}})

# Setup entrypoint script
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh
ENTRYPOINT ["/entrypoint.sh"]
