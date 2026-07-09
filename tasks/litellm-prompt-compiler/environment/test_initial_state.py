import importlib.util
import json
import os

import pytest
import yaml

PROJECT_DIR = "/home/user/myproject"
HANDLE = "support-triage-agent"
MATERIALIZED_PATH = os.path.join(
    PROJECT_DIR, "prompts", ".materialized", f"{HANDLE}.prompt.yaml"
)
REQUIRED_VARIABLES = ["customer_name", "account_tier", "issue_summary", "priority"]


def test_langwatch_importable():
    assert (
        importlib.util.find_spec("langwatch") is not None
    ), "The 'langwatch' Python package must be installed and importable."


def test_litellm_importable():
    assert (
        importlib.util.find_spec("litellm") is not None
    ), "The 'litellm' Python package must be installed and importable."


def test_project_dir_exists():
    assert os.path.isdir(
        PROJECT_DIR
    ), f"Project directory {PROJECT_DIR} does not exist."


def test_prompts_json_exists():
    path = os.path.join(PROJECT_DIR, "prompts.json")
    assert os.path.isfile(path), f"Expected pre-provisioned file {path} to exist."
    with open(path) as f:
        data = json.load(f)
    assert (
        "prompts" in data and HANDLE in data["prompts"]
    ), f"prompts.json must declare the '{HANDLE}' dependency."


def test_prompts_lock_resolves_version_two():
    path = os.path.join(PROJECT_DIR, "prompts-lock.json")
    assert os.path.isfile(path), f"Expected pre-provisioned file {path} to exist."
    with open(path) as f:
        data = json.load(f)
    prompts = data.get("prompts", {})
    assert HANDLE in prompts, f"prompts-lock.json must contain an entry for '{HANDLE}'."
    entry = prompts[HANDLE]
    assert (
        int(entry.get("version")) == 2
    ), f"prompts-lock.json must resolve '{HANDLE}' to integer version 2."
    assert entry.get(
        "materialized"
    ), "prompts-lock.json entry must record a materialized file path."


def test_materialized_prompt_exists_and_is_wellformed():
    assert os.path.isfile(
        MATERIALIZED_PATH
    ), f"Expected materialized prompt {MATERIALIZED_PATH} to exist."
    with open(MATERIALIZED_PATH) as f:
        data = yaml.safe_load(f)
    model = data.get("model", "")
    assert isinstance(model, str) and model.startswith(
        "openai/"
    ), "Materialized prompt 'model' must be a provider-prefixed 'openai/...' string."
    messages = data.get("messages", [])
    roles = {m.get("role") for m in messages}
    assert (
        "system" in roles and "user" in roles
    ), "Materialized prompt must contain at least one system and one user message."


def test_materialized_prompt_references_all_variables():
    with open(MATERIALIZED_PATH) as f:
        data = yaml.safe_load(f)
    combined = "".join(m.get("content", "") for m in data.get("messages", []))
    for var in REQUIRED_VARIABLES:
        assert (
            "{{" + var + "}}" in combined or "{{ " + var + " }}" in combined
        ), f"Materialized prompt must reference the template variable '{{{{{var}}}}}'."
