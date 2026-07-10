import os
import subprocess
import json
import pytest

PROJECT_DIR = "/home/user/myproject"
VENV_PYTHON = os.path.join(PROJECT_DIR, ".venv", "bin", "python3")

@pytest.fixture(scope="session", autouse=True)
def setup_environment():
    """Setup the virtual environment and install dependencies as defined in truth."""
    # Run uv venv
    subprocess.run(["uv", "venv"], cwd=PROJECT_DIR, check=True)

    # Setup environment variables to simulate activating the venv
    venv_dir = os.path.join(PROJECT_DIR, ".venv")
    env = os.environ.copy()
    env["VIRTUAL_ENV"] = venv_dir
    env["PATH"] = f"{os.path.join(venv_dir, 'bin')}:{env.get('PATH', '')}"

    # Run uv pip install
    subprocess.run(
        ["uv", "pip", "install", "langwatch-scenario"],
        cwd=PROJECT_DIR,
        env=env,
        check=True
    )

def test_scenario_script_output():
    """Run the script and verify the JSON output matches the expected scenario configuration."""
    result = subprocess.run(
        [VENV_PYTHON, "scenario_def.py", "--run-id", "test-run-999"],
        cwd=PROJECT_DIR,
        capture_output=True,
        text=True
    )

    assert result.returncode == 0, f"Script execution failed. Stderr: {result.stderr}"

    try:
        output_data = json.loads(result.stdout)
    except json.JSONDecodeError:
        pytest.fail(f"Failed to parse stdout as JSON. Stdout: {result.stdout}")

    # Verify name
    assert output_data.get("name") == "Refund Scenario test-run-999", \
        f"Expected name to be 'Refund Scenario test-run-999', got: {output_data.get('name')}"

    # Verify agents list
    agents = output_data.get("agents", [])
    assert isinstance(agents, list) and len(agents) == 4, \
        f"Expected exactly 4 agents, got {len(agents)}: {agents}"

    assert "SupportAgentAdapter" in agents, "Missing SupportAgentAdapter in agents"
    assert "UserSimulatorAgent" in agents, "Missing UserSimulatorAgent in agents"
    assert agents.count("JudgeAgent") == 2, f"Expected exactly 2 JudgeAgents, got: {agents.count('JudgeAgent')}"

    # Verify judge_criteria
    judge_criteria = output_data.get("judge_criteria", [])
    assert isinstance(judge_criteria, list) and len(judge_criteria) == 2, \
        f"Expected exactly 2 elements in judge_criteria, got {len(judge_criteria)}"
    assert all(isinstance(criteria, list) and all(isinstance(c, str) for c in criteria) for criteria in judge_criteria), \
        f"Expected judge_criteria to be a list of string lists, got: {judge_criteria}"

    # Verify script_types
    script_types = output_data.get("script_types", [])
    expected_script_types = ["user", "agent", "succeed"]
    assert script_types == expected_script_types, \
        f"Expected script_types to be {expected_script_types}, got: {script_types}"
