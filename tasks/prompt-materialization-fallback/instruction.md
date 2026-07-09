# LangWatch Prompt Materialization with Offline Fallback Loader

## Background
You are hardening the prompt-delivery path of a Python service that uses [LangWatch Prompt Management](https://langwatch.ai/docs/prompt-management/getting-started). In production the service fetches versioned prompts from the LangWatch API, but the deployment target is an air-gapped / CI environment where the LangWatch API can be unreachable. To keep the service running under LangWatch's *Guaranteed Availability* model, prompts are materialized to local YAML files with the Prompts CLI and the application must transparently fall back to that local cache.

Your job is to (1) scaffold and materialize a versioned prompt locally as YAML, and (2) implement a robust, deterministic fallback loader plus a small CLI that compiles the prompt with dynamic variables — working correctly even when the LangWatch API is not reachable.

## Requirements
- Scaffold a LangWatch prompts project so that the following tracking files exist at the project root: `prompts.json` and `prompts-lock.json`.
- Provide a locally materialized, versioned prompt for the handle `customer-support-bot` at `prompts/.materialized/customer-support-bot.prompt.yaml`. The prompt must:
  - Use a model identifier of the form `openai/<model>` (e.g. `openai/gpt-4o-mini`).
  - Contain at least a `system` message and a `user` message.
  - Reference the two template variables `{{user_name}}` and `{{issue}}` (the `{{...}}` mustache syntax used by LangWatch prompts) across its messages.
- `prompts-lock.json` must resolve the `customer-support-bot` dependency to a concrete integer version (use version `3`) and record the path to the materialized YAML file.
- Implement a Python CLI application `run.py` that loads the prompt through a fallback loader and compiles it with runtime variables.
- The fallback loader must be **deterministic and offline-capable**: when the application runs in offline mode it must load the prompt strictly from the local materialized cache (never depending on a network call), and report where the prompt was sourced from.
- Variable compilation must substitute every `{{variable}}` placeholder with the provided value and must fail loudly (non-zero exit) if a required variable is missing. No `{{` / `}}` placeholders may remain in the compiled output.
- Do NOT mock LangWatch, its HTTP client, or any transitive dependency. The real `langwatch` package must be installed and importable.

## Implementation Hints
- Use the LangWatch Prompts CLI (`langwatch prompt init`, `langwatch prompt create`) to scaffold the project layout and the prompt YAML. The CLI is available in the environment. Creating/initializing prompts is a local operation and does not require network access.
- Materialized prompts live under `prompts/.materialized/` and follow the `.prompt.yaml` format (`model`, optional `modelParameters`, and a `messages` list of `{role, content}`). See the [Prompts CLI](https://langwatch.ai/docs/prompt-management/cli) and [Guaranteed Availability](https://langwatch.ai/docs/prompt-management/features/advanced/guaranteed-availability) docs.
- For the offline path, resolve the materialized file location from `prompts-lock.json` and parse the YAML yourself rather than assuming a network fetch. Note: pointing `LANGWATCH_ENDPOINT` at a bad address does not reliably raise a network error, so drive the fallback with an explicit offline execution path instead.
- Implement mustache-style `{{variable}}` substitution deterministically. Collect the set of variables referenced by the template to decide which ones are required.
- Use `uv` to create the virtualenv and install Python packages (`uv venv`, then `uv pip install ...`).

## Acceptance Criteria
- Project path: /home/user/myproject
- Command: `python run.py --handle <handle> --vars <json_object> [--version <int>] [--offline] --out <path>`
  - `--handle`: the prompt handle to load (e.g. `customer-support-bot`).
  - `--vars`: a JSON object string mapping variable names to string values.
  - `--version`: optional integer version; when omitted, the version recorded in `prompts-lock.json` is used.
  - `--offline`: when present, the loader must load only from the local materialized cache.
  - `--out`: path to write the compiled result JSON.
- The command writes a JSON object to the `--out` path with this shape:
  ```json
  {
    "handle": string,
    "version": integer,
    "model": string,
    "source": string,
    "messages": [ { "role": string, "content": string } ]
  }
  ```
  - `source` is `"local_materialized"` when the prompt was loaded from the local cache and `"remote_api"` when loaded from the LangWatch API.
  - When `--offline` is passed, `source` must be `"local_materialized"`.
  - `model` must be the model string from the materialized prompt (begins with `openai/`).
  - `version` must be the resolved integer version.
  - Every message `content` must have all `{{...}}` placeholders replaced; no `{{` substring may remain.
- Required artifacts at the project root: `prompts.json`, `prompts-lock.json`, and `prompts/.materialized/customer-support-bot.prompt.yaml`.
- Error handling: if a required template variable is not supplied in `--vars`, the command must exit with a non-zero status and must not write a successful compiled output. If `--offline` is set and the materialized file cannot be found, the command must also exit non-zero.

