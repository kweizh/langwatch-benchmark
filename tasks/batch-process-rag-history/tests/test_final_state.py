import os
import subprocess
import json

PROJECT_DIR = "/home/user/myproject"

def get_run_id():
    with open("/logs/artifacts/run-id", "r") as f:
        return f.read().strip()

def test_process_rag_cli():
    run_id = get_run_id()
    output_file = f"summary_{run_id}.json"
    output_path = os.path.join(PROJECT_DIR, output_file)

    # Setup: clean up existing output file if any
    if os.path.exists(output_path):
        os.remove(output_path)

    # Verification Step 2: Run the command
    result = subprocess.run(
        ["python3", "process_rag.py", "--input", "rag_history.csv", "--output", output_file],
        cwd=PROJECT_DIR,
        capture_output=True,
        text=True
    )

    assert result.returncode == 0, f"Command failed with exit code {result.returncode}.\nStdout: {result.stdout}\nStderr: {result.stderr}"
    assert "field_size_limit" not in result.stderr.lower(), "CSV field size limit error found in stderr."
    assert "413 payload too large" not in result.stderr.lower(), "LangWatch API 413 Payload Too Large error found in stderr."

    # Verification Step 3: Check output file exists
    assert os.path.isfile(output_path), f"Output JSON file {output_path} was not created."

    # Verification Step 4: Check JSON contents
    with open(output_path, "r") as f:
        try:
            summary = json.load(f)
        except json.JSONDecodeError as e:
            assert False, f"Output file is not valid JSON: {e}"

    assert "total_processed" in summary, "Missing 'total_processed' field in output JSON."
    assert "total_passed" in summary, "Missing 'total_passed' field in output JSON."
    assert "total_failed" in summary, "Missing 'total_failed' field in output JSON."

    # Since we know the test data (which will be generated in Dockerfile), we can assert exact values
    # For now, we assert they are integers.
    assert isinstance(summary["total_processed"], int), "'total_processed' must be an integer."
    assert isinstance(summary["total_passed"], int), "'total_passed' must be an integer."
    assert isinstance(summary["total_failed"], int), "'total_failed' must be an integer."
