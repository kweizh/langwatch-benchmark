import json
import os
import shutil
import subprocess

import yaml

PROJECT_DIR = "/home/user/myproject"
PROMPTS_JSON = os.path.join(PROJECT_DIR, "prompts.json")
LOCK_JSON = os.path.join(PROJECT_DIR, "prompts-lock.json")
MATERIALIZED = os.path.join(
    PROJECT_DIR, "prompts", ".materialized", "customer-support-bot.prompt.yaml"
)
OUT = os.path.join(PROJECT_DIR, "compiled_output.json")

HANDLE = "customer-support-bot"
USER_NAME = "Alice Chen"
ISSUE = "I was double charged for my subscription"
FULL_VARS = json.dumps({"user_name": USER_NAME, "issue": ISSUE})
MISSING_VARS = json.dumps({"user_name": USER_NAME})
SENTINEL = "SENTINEL_ZLT_9F3A"


def _python():
    venv_python = os.path.join(PROJECT_DIR, ".venv", "bin", "python")
    return venv_python if os.path.isfile(venv_python) else "python3"


def _run_cli(vars_json, offline=True, out=OUT, version=None):
    args = [_python(), "run.py", "--handle", HANDLE, "--vars", vars_json]
    if version is not None:
        args += ["--version", str(version)]
    if offline:
        args += ["--offline"]
    args += ["--out", out]
    return subprocess.run(args, capture_output=True, text=True, cwd=PROJECT_DIR)


def _extract_lock_version(lock_data):
    prompts = lock_data.get("prompts", {})
    entry = prompts.get(HANDLE)
    if entry is None:
        return None
    if isinstance(entry, dict):
        return entry.get("version")
    return entry


# ---------------------------------------------------------------------------
# Step 1: Required artifacts exist and are well-formed.
# ---------------------------------------------------------------------------
def test_prompts_json_exists():
    assert os.path.isfile(PROMPTS_JSON), (
        f"Expected prompt dependency file at {PROMPTS_JSON}."
    )


def test_lock_file_resolves_version_and_materialized_path():
    assert os.path.isfile(LOCK_JSON), f"Expected lock file at {LOCK_JSON}."
    with open(LOCK_JSON) as f:
        raw = f.read()
    data = json.loads(raw)
    version = _extract_lock_version(data)
    assert version is not None, (
        f"Lock file {LOCK_JSON} does not contain an entry for handle '{HANDLE}'."
    )
    assert int(str(version).strip()) == 3, (
        f"Expected '{HANDLE}' to resolve to integer version 3 in the lock file, got {version!r}."
    )
    assert ".materialized" in raw, (
        "Lock file does not reference a materialized YAML file path."
    )


def test_materialized_prompt_is_valid():
    assert os.path.isfile(MATERIALIZED), (
        f"Expected materialized prompt at {MATERIALIZED}."
    )
    with open(MATERIALIZED) as f:
        prompt = yaml.safe_load(f)
    assert isinstance(prompt, dict), "Materialized prompt YAML must parse to a mapping."
    model = prompt.get("model", "")
    assert isinstance(model, str) and model.startswith("openai/"), (
        f"Materialized prompt 'model' must start with 'openai/', got {model!r}."
    )
    messages = prompt.get("messages", [])
    assert isinstance(messages, list) and messages, (
        "Materialized prompt must contain a non-empty 'messages' list."
    )
    roles = {m.get("role") for m in messages if isinstance(m, dict)}
    assert "system" in roles, "Materialized prompt must contain a 'system' message."
    assert "user" in roles, "Materialized prompt must contain a 'user' message."
    combined = "".join(
        str(m.get("content", "")) for m in messages if isinstance(m, dict)
    )
    assert "{{user_name}}" in combined, (
        "Materialized prompt must reference the {{user_name}} template variable."
    )
    assert "{{issue}}" in combined, (
        "Materialized prompt must reference the {{issue}} template variable."
    )


# ---------------------------------------------------------------------------
# Step 2: Offline compile happy path.
# ---------------------------------------------------------------------------
def test_offline_compile_happy_path():
    if os.path.exists(OUT):
        os.remove(OUT)
    result = _run_cli(FULL_VARS, offline=True)
    assert result.returncode == 0, (
        f"Offline compile failed (exit {result.returncode}).\n"
        f"STDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}"
    )
    assert os.path.isfile(OUT), f"Expected compiled output written to {OUT}."
    with open(OUT) as f:
        data = json.load(f)

    assert data.get("handle") == HANDLE, (
        f"Expected handle '{HANDLE}' in output, got {data.get('handle')!r}."
    )
    assert data.get("version") == 3, (
        f"Expected resolved version 3 in output, got {data.get('version')!r}."
    )
    assert data.get("source") == "local_materialized", (
        f"Expected source 'local_materialized' for offline run, got {data.get('source')!r}."
    )
    model = data.get("model", "")
    assert isinstance(model, str) and model.startswith("openai/"), (
        f"Expected model starting with 'openai/', got {model!r}."
    )

    messages = data.get("messages", [])
    assert isinstance(messages, list) and messages, (
        "Compiled output must contain a non-empty 'messages' list."
    )
    roles = {m.get("role") for m in messages if isinstance(m, dict)}
    assert "system" in roles and "user" in roles, (
        f"Compiled output must contain both 'system' and 'user' messages, got roles {roles}."
    )
    combined = "".join(
        str(m.get("content", "")) for m in messages if isinstance(m, dict)
    )
    assert USER_NAME in combined, (
        f"Expected the substituted user_name '{USER_NAME}' in the compiled messages."
    )
    assert ISSUE in combined, (
        f"Expected the substituted issue text '{ISSUE}' in the compiled messages."
    )
    assert "{{" not in combined, (
        "Compiled messages must not contain any unresolved '{{' placeholders."
    )


# ---------------------------------------------------------------------------
# Step 3: Loader truly reads the local materialized cache (sentinel test).
# ---------------------------------------------------------------------------
def test_loader_reads_local_materialized_cache():
    with open(MATERIALIZED, "rb") as f:
        original = f.read()
    try:
        prompt = yaml.safe_load(original.decode("utf-8"))
        for message in prompt.get("messages", []):
            if isinstance(message, dict) and message.get("role") == "system":
                message["content"] = f"{message.get('content', '')} {SENTINEL}"
                break
        with open(MATERIALIZED, "w") as f:
            yaml.safe_dump(prompt, f, allow_unicode=True, sort_keys=False)

        if os.path.exists(OUT):
            os.remove(OUT)
        result = _run_cli(FULL_VARS, offline=True)
        assert result.returncode == 0, (
            f"Offline compile failed after injecting sentinel.\n"
            f"STDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}"
        )
        with open(OUT) as f:
            data = json.load(f)
        combined = "".join(
            str(m.get("content", "")) for m in data.get("messages", [])
            if isinstance(m, dict)
        )
        assert SENTINEL in combined, (
            "Sentinel token injected into the local materialized file did not appear "
            "in the compiled output; the loader is not reading from the local cache."
        )
    finally:
        with open(MATERIALIZED, "wb") as f:
            f.write(original)


# ---------------------------------------------------------------------------
# Step 4: Missing required variable fails.
# ---------------------------------------------------------------------------
def test_missing_required_variable_fails():
    if os.path.exists(OUT):
        os.remove(OUT)
    result = _run_cli(MISSING_VARS, offline=True)
    assert result.returncode != 0, (
        "Compiling with a missing required variable ('issue') must exit non-zero, "
        f"but it succeeded.\nSTDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}"
    )
    combined_err = (result.stdout + result.stderr).lower()
    assert "issue" in combined_err, (
        "Expected the error output to mention the missing variable 'issue'.\n"
        f"STDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}"
    )
    if os.path.isfile(OUT):
        with open(OUT) as f:
            try:
                data = json.load(f)
            except json.JSONDecodeError:
                data = {}
        combined = "".join(
            str(m.get("content", "")) for m in data.get("messages", [])
            if isinstance(m, dict)
        )
        assert "{{" in combined or ISSUE not in combined, (
            "A fully compiled successful output must not be produced when a required "
            "variable is missing."
        )


# ---------------------------------------------------------------------------
# Step 5: Missing materialized cache in offline mode fails.
# ---------------------------------------------------------------------------
def test_missing_materialized_cache_offline_fails():
    backup = MATERIALIZED + ".bak"
    shutil.move(MATERIALIZED, backup)
    try:
        if os.path.exists(OUT):
            os.remove(OUT)
        result = _run_cli(FULL_VARS, offline=True)
        assert result.returncode != 0, (
            "Offline compile must fail when the materialized cache file is missing, "
            f"but it exited 0.\nSTDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}"
        )
    finally:
        shutil.move(backup, MATERIALIZED)
