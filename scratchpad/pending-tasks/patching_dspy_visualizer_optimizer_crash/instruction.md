Integrating the LangWatch DSPy tracker with certain optimizers like `SIMBA` causes the initialization to fail with a `ValueError` because the visualizer explicitly restricts the list of supported optimizers to a predefined set (e.g., `BootstrapFewShot`, `MIPROv2`).

You need to patch the provided `langwatch/dspy/visualizer.py` initialization logic to properly accept and parse the `SIMBA` optimizer without throwing an unhandled exception.

**Constraints:**
- Do not remove or break support for currently supported optimizers (e.g., `BootstrapFewShotWithRandomSearch`, `COPRO`).
- The fix must bypass the strict `ValueError` check specifically for `SIMBA` and map it to a generic optimizer tracking schema.