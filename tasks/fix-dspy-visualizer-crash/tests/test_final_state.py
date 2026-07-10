import os
import subprocess
import pytest

PROJECT_DIR = "/home/user/myproject"
VENV_PYTHON = os.path.join(PROJECT_DIR, ".venv", "bin", "python")

def test_script_execution():
    """Run the script and verify it completes successfully and outputs the expected message."""
    script_path = os.path.join(PROJECT_DIR, "optimize.py")

    # If the venv python doesn't exist, fallback to system python
    python_exec = VENV_PYTHON if os.path.exists(VENV_PYTHON) else "python3"

    result = subprocess.run(
        [python_exec, script_path],
        capture_output=True,
        text=True,
        cwd=PROJECT_DIR
    )

    assert result.returncode == 0, f"Script execution failed with exit code {result.returncode}.\nStdout: {result.stdout}\nStderr: {result.stderr}"
    assert "Optimization completed successfully" in result.stdout, "Expected 'Optimization completed successfully' in stdout."

def test_code_no_longer_uses_simba():
    """Verify that the code has been updated to use a supported optimizer instead of SIMBA."""
    script_path = os.path.join(PROJECT_DIR, "optimize.py")

    with open(script_path, "r") as f:
        content = f.read()

    assert "SIMBA" not in content, "The script still contains 'SIMBA', which is an unsupported optimizer."

    # Check for supported optimizers
    supported_optimizers = ["BootstrapFewShotWithRandomSearch", "BootstrapFewShot", "COPRO", "MIPROv2"]
    found_supported = any(opt in content for opt in supported_optimizers)

    assert found_supported, f"The script must use one of the supported optimizers: {', '.join(supported_optimizers)}."
