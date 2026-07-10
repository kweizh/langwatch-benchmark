# Fix DSPy Visualizer Crash

## Background
You have a DSPy optimization script that integrates with LangWatch for tracing and visualization. However, the script currently crashes during the optimizer setup with a `ValueError` because the chosen optimizer (`SIMBA`) is not supported by the LangWatch DSPy visualizer.

## Requirements
- Modify the provided `/home/user/myproject/optimize.py` script to use a DSPy optimizer that is supported by LangWatch (e.g., `BootstrapFewShotWithRandomSearch`).
- Ensure the script runs successfully without throwing the `ValueError`.
- The script must output the string `Optimization completed successfully` to standard output when finished.

## Implementation Hints
- Review the error message from LangWatch to identify which optimizers are supported.
- Change the optimizer instantiation in the script to one of the supported optimizers.
- You may need to adjust the optimizer arguments if the new optimizer requires different parameters than `SIMBA`.
- Do not remove the LangWatch tracking integration.

## Acceptance Criteria
- Project path: /home/user/myproject
- Command: python3 optimize.py
- The command must execute successfully (exit code 0).
- The command stdout must include: `Optimization completed successfully`.

