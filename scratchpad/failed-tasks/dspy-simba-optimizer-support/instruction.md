# Extend the LangWatch DSPy Visualizer to Support the SIMBA Optimizer

## Background
LangWatch ships a DSPy visualization tracker (`langwatch.dspy`). When you call `langwatch.dspy.init(experiment=..., optimizer=<optimizer>)`, LangWatch swaps the optimizer's class for a tracking-enabled subclass so that each optimization step (its score and the resulting predictors) is streamed to the LangWatch backend.

The tracker only recognises a fixed allow-list of optimizers. Passing DSPy's newer `SIMBA` (Stochastic Introspective Mini-Batch Ascent) optimizer makes initialization crash:

```
ValueError: Optimizer SIMBA is not supported by LangWatch DSPy visualizer yet, only [BootstrapFewShot, BootstrapFewShotWithRandomSearch, COPRO, MIPROv2] are supported, please open an issue: https://github.com/langwatch/langwatch/issues
```

This is tracked upstream as GitHub issue #496. Your job is to extend the visualizer so that `SIMBA` becomes a first-class, tracked optimizer.

## Requirements
- Add SIMBA support to the LangWatch DSPy visualizer **at runtime**, without editing the installed `langwatch` package files. Do this from a module `simba_support.py` that exposes an idempotent function `register_langwatch_simba()`.
- After `register_langwatch_simba()` has been called, initializing the tracker with a real `dspy.teleprompt.SIMBA` instance (`langwatch.dspy.init(experiment=..., optimizer=<SIMBA>)`) must succeed and must NOT raise the `ValueError` above.
- When SIMBA runs, the visualizer must emit one LangWatch DSPy step per candidate program that SIMBA produces, using LangWatch's normal step-logging path (the same `log_step` mechanism the built-in optimizers use). Each step must carry the candidate's score, its predictors, and identify the optimizer as `SIMBA`.
- Provide a runnable CLI `run.py` that performs a small, self-contained, deterministic SIMBA optimization with tracking enabled against the configured LangWatch endpoint, and records the emitted steps as JSON to a log file.
- Never mock the `langwatch` SDK, DSPy, or their HTTP/OpenTelemetry dependencies. Read the LangWatch endpoint and API key from environment variables.

## Implementation Hints
- Study how LangWatch decides which optimizers are supported. The relevant logic lives in `langwatch.dspy` where an optimizer's class is looked up in a class map and, if absent, a `ValueError` is raised. Extending support means teaching that lookup about SIMBA and providing a tracking-enabled SIMBA subclass, analogous to the existing `LangWatchTracked*` optimizer classes.
- The built-in tracked optimizers wrap their metric with `langwatch.dspy`'s metric tracking and call the tracker's `log_step(...)` with a `DSPyOptimizer`, an index, a score, a label, and a list of `DSPyPredictor` objects. Reuse those same building blocks so your steps are serialized and shipped identically.
- DSPy's `SIMBA.compile(...)` returns the best program with two useful attributes attached: `candidate_programs` (a score-sorted list of `{"score", "program"}` dicts) and `trial_logs`. These give you both the scores and the programs (and therefore their predictors) you need to build steps after compilation finishes.
- Because LangWatch wraps the metric before SIMBA calls it, make sure the metric you hand to SIMBA tolerates being called with a `trace` keyword argument.
- For a deterministic, offline run in `run.py`, configure DSPy with a local test LM (e.g. DSPy's built-in dummy LM) and a fixed `seed`, keep `bsize` small and `len(trainset) >= bsize`, and use a metric whose score depends only on the example so results are stable even without a real model. DSPy's SIMBA already swallows per-program execution errors, so the run completes and still attaches `candidate_programs`.
- `langwatch.dspy` uses `LANGWATCH_ENDPOINT` and `LANGWATCH_API_KEY` from the environment. `init` POSTs to `/api/experiment/init` and step logging POSTs to `/api/dspy/log_steps`.

## Acceptance Criteria
- Project path: /home/user/project
- Dependencies `langwatch` and `dspy` are already installed in a virtual environment at /home/user/project/.venv (installed with `uv`). Run everything with that environment's interpreter.
- Module: /home/user/project/simba_support.py exposes a callable `register_langwatch_simba()` that is idempotent (safe to call multiple times).
- Registration effect: after calling `register_langwatch_simba()`, calling `langwatch.dspy.langwatch_dspy.patch_optimizer(opt)` on a fresh `dspy.teleprompt.SIMBA` instance must not raise, and must convert `opt` into an instance that is still a subclass of `dspy.teleprompt.SIMBA`.
- Command: `python3 run.py` (run with the project's virtual environment). It reads `LANGWATCH_ENDPOINT` and `LANGWATCH_API_KEY` from the environment and reads the current run id from `/logs/artifacts/run-id`.
- Running `run.py` performs a real, tracked SIMBA optimization: it registers SIMBA support, calls `langwatch.dspy.init(...)` with a `SIMBA` optimizer (no `ValueError`), runs `SIMBA.compile(...)`, and as a side effect the LangWatch endpoint receives an experiment-init POST followed by one or more step POSTs to `/api/dspy/log_steps`.
- Output file: /home/user/project/output.log must contain a single line beginning with `Steps JSON: ` followed by a JSON array of the emitted steps. Other log output may appear on other lines; the JSON must be parseable from that one line.
- Each step object in that JSON array, and each step delivered to `/api/dspy/log_steps`, must include: `index` (string), `score` (number), `label` (string), an `optimizer` object whose `name` equals `"SIMBA"` and whose `parameters` object includes the keys `bsize`, `num_candidates`, `max_steps`, and `max_demos`, and a non-empty `predictors` array.
- The number of emitted steps must equal the number of entries in the compiled program's `candidate_programs`.
- The experiment slug/name used for the run must incorporate the run id read from `/logs/artifacts/run-id`.

