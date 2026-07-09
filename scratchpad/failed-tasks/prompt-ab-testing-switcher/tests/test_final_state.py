import json
import os
import subprocess

import pytest
import yaml

PROJECT_DIR = "/home/user/myproject"
PROMPTS_JSON = os.path.join(PROJECT_DIR, "prompts.json")
PROMPTS_DIR = os.path.join(PROJECT_DIR, "prompts")

VARIANTS = {
    "concise": "support-reply-concise",
    "empathetic": "support-reply-empathetic",
    "detailed": "support-reply-detailed",
}
WEIGHTS = {"concise": 0.2, "empathetic": 0.5, "detailed": 0.3}
TOLERANCE = 0.04

CUSTOMER_NAME = "Dana Lopez"
QUESTION = "Why was I charged twice?"
FULL_VARS = json.dumps({"customer_name": CUSTOMER_NAME, "question": QUESTION})
MISSING_VARS = json.dumps({"customer_name": CUSTOMER_NAME})


def _variant_yaml_path(handle):
    return os.path.join(PROMPTS_DIR, f"{handle}.prompt.yaml")


def _run_switch(iterations, seed, vars_json, out_path, spanlog_path):
    args = [
        "npm",
        "run",
        "switch",
        "--",
        "--iterations",
        str(iterations),
        "--seed",
        str(seed),
        "--vars",
        vars_json,
        "--out",
        out_path,
        "--spanlog",
        spanlog_path,
    ]
    return subprocess.run(
        args, capture_output=True, text=True, cwd=PROJECT_DIR, timeout=600
    )


def _cleanup(*paths):
    for p in paths:
        try:
            if os.path.isfile(p):
                os.remove(p)
        except OSError:
            pass


def _load_json_file(path):
    with open(path) as f:
        return json.load(f)


def _read_ndjson(path):
    spans = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            spans.append(json.loads(line))
    return spans


def _joined_content(messages):
    return "".join(
        str(m.get("content", "")) for m in messages if isinstance(m, dict)
    )


def _flatten_attrs(span):
    """Return a flat dict of attribute-key -> value for a span object.

    Different exporters serialise OTel attributes differently (nested under
    'attributes', as a list of {key,value}, etc.). Normalise the common shapes.
    """
    attrs = span.get("attributes", span)
    flat = {}
    if isinstance(attrs, dict):
        for k, v in attrs.items():
            flat[str(k)] = v
    elif isinstance(attrs, list):
        for item in attrs:
            if isinstance(item, dict) and "key" in item:
                val = item.get("value")
                if isinstance(val, dict):
                    # OTLP value shape e.g. {"stringValue": "..."}
                    val = next(iter(val.values()), val)
                flat[str(item["key"])] = val
    return flat


def _span_variant_id(span):
    flat = _flatten_attrs(span)
    for k, v in flat.items():
        kl = k.lower()
        if "variant" in kl and ("id" in kl or kl.endswith("variant")):
            return str(v)
    return None


def _span_handle(span):
    flat = _flatten_attrs(span)
    for k, v in flat.items():
        if "handle" in k.lower():
            return str(v)
    return None


def _span_type_is_prompt(span):
    flat = _flatten_attrs(span)
    for k, v in flat.items():
        if k.lower().endswith("span.type") or k.lower().endswith("type"):
            if str(v).lower() == "prompt":
                return True
    # Fall back to span name / top-level type field
    for key in ("type", "spanType", "span_type"):
        if str(span.get(key, "")).lower() == "prompt":
            return True
    return False


def _span_id(span):
    for key in ("spanId", "span_id", "spanID"):
        if key in span and span[key]:
            return str(span[key])
    ctx = span.get("spanContext") or span.get("context") or {}
    if isinstance(ctx, dict):
        for key in ("spanId", "span_id", "spanID"):
            if key in ctx and ctx[key]:
                return str(ctx[key])
    return None


def _span_version_is_int(span):
    flat = _flatten_attrs(span)
    for k, v in flat.items():
        if "version" in k.lower():
            try:
                int(v)
                return True
            except (TypeError, ValueError):
                continue
    return False


# ---------------------------------------------------------------------------
# Session-scoped main run (3000 iterations) shared across tests.
# ---------------------------------------------------------------------------
@pytest.fixture(scope="session")
def main_run():
    out_path = "/tmp/ab_out_main.json"
    spanlog_path = "/tmp/ab_spans_main.jsonl"
    _cleanup(out_path, spanlog_path)
    result = _run_switch(3000, 424242, FULL_VARS, out_path, spanlog_path)
    assert result.returncode == 0, (
        f"Happy-path run failed (exit {result.returncode}).\n"
        f"STDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}"
    )
    assert os.path.isfile(out_path), f"Expected run summary at {out_path}."
    assert os.path.isfile(spanlog_path), f"Expected span log at {spanlog_path}."
    data = _load_json_file(out_path)
    spans = _read_ndjson(spanlog_path)
    return data, spans


# ---------------------------------------------------------------------------
# Step 1: Required artifacts exist and are well-formed.
# ---------------------------------------------------------------------------
def test_prompts_json_exists():
    assert os.path.isfile(PROMPTS_JSON), (
        f"Expected LangWatch prompt tracking file at {PROMPTS_JSON}."
    )


@pytest.mark.parametrize("variant_id,handle", list(VARIANTS.items()))
def test_variant_prompt_yaml_is_valid(variant_id, handle):
    path = _variant_yaml_path(handle)
    assert os.path.isfile(path), (
        f"Expected variant prompt file for '{variant_id}' at {path}."
    )
    with open(path) as f:
        prompt = yaml.safe_load(f)
    assert isinstance(prompt, dict), f"Variant YAML {path} must parse to a mapping."
    model = prompt.get("model", "")
    assert isinstance(model, str) and model.startswith("openai/"), (
        f"Variant '{variant_id}' model must start with 'openai/', got {model!r}."
    )
    messages = prompt.get("messages", [])
    assert isinstance(messages, list) and messages, (
        f"Variant '{variant_id}' must contain a non-empty 'messages' list."
    )
    roles = {m.get("role") for m in messages if isinstance(m, dict)}
    assert "system" in roles, f"Variant '{variant_id}' must contain a 'system' message."
    assert "user" in roles, f"Variant '{variant_id}' must contain a 'user' message."
    combined = _joined_content(messages)
    assert "{{customer_name}}" in combined, (
        f"Variant '{variant_id}' must reference the {{{{customer_name}}}} template variable."
    )
    assert "{{question}}" in combined, (
        f"Variant '{variant_id}' must reference the {{{{question}}}} template variable."
    )
    system_content = "".join(
        str(m.get("content", ""))
        for m in messages
        if isinstance(m, dict) and m.get("role") == "system"
    )
    assert variant_id in system_content, (
        f"Variant '{variant_id}' system message must contain its own id token '{variant_id}'."
    )


# ---------------------------------------------------------------------------
# Step 2: Output schema, compilation, and distribution.
# ---------------------------------------------------------------------------
def test_out_summary_schema_and_seed(main_run):
    data, _ = main_run
    assert data.get("seed") == 424242, (
        f"Expected seed 424242 in summary, got {data.get('seed')!r}."
    )
    assert data.get("iterations") == 3000, (
        f"Expected iterations 3000 in summary, got {data.get('iterations')!r}."
    )
    variants = data.get("variants", [])
    assert isinstance(variants, list) and len(variants) == 3, (
        "Summary 'variants' must list the three configured variants."
    )
    by_id = {v.get("id"): v for v in variants if isinstance(v, dict)}
    assert set(by_id.keys()) == set(VARIANTS.keys()), (
        f"Expected variant ids {set(VARIANTS.keys())}, got {set(by_id.keys())}."
    )
    for vid, handle in VARIANTS.items():
        assert by_id[vid].get("handle") == handle, (
            f"Variant '{vid}' must map to handle '{handle}', got {by_id[vid].get('handle')!r}."
        )
        assert abs(float(by_id[vid].get("weight")) - WEIGHTS[vid]) < 1e-6, (
            f"Variant '{vid}' weight must be {WEIGHTS[vid]}, got {by_id[vid].get('weight')!r}."
        )


def test_selections_and_distribution(main_run):
    data, _ = main_run
    selections = data.get("selections", [])
    assert isinstance(selections, list) and len(selections) == 3000, (
        f"Expected exactly 3000 selections, got {len(selections)}."
    )
    for s in selections:
        assert s.get("variantId") in VARIANTS, (
            f"Selection has unknown variantId {s.get('variantId')!r}."
        )
    tally = {}
    for s in selections:
        tally[s["variantId"]] = tally.get(s["variantId"], 0) + 1

    distribution = data.get("distribution", {})
    assert sum(distribution.values()) == 3000, (
        f"Distribution counts must sum to 3000, got {sum(distribution.values())}."
    )
    for vid in VARIANTS:
        assert distribution.get(vid, 0) == tally.get(vid, 0), (
            f"Distribution for '{vid}' ({distribution.get(vid)}) does not match "
            f"the tally of selections ({tally.get(vid)})."
        )
        freq = tally.get(vid, 0) / 3000.0
        assert abs(freq - WEIGHTS[vid]) < TOLERANCE, (
            f"Observed frequency for '{vid}' was {freq:.3f}, expected ~{WEIGHTS[vid]} "
            f"(tolerance {TOLERANCE})."
        )
        assert tally.get(vid, 0) > 0, f"Variant '{vid}' was never selected."


def test_compiled_messages_are_correct(main_run):
    data, _ = main_run
    for s in data.get("selections", []):
        model = s.get("model", "")
        assert isinstance(model, str) and model.startswith("openai/"), (
            f"Selection model must start with 'openai/', got {model!r}."
        )
        assert isinstance(s.get("version"), int), (
            f"Selection version must be an integer, got {s.get('version')!r}."
        )
        messages = s.get("messages", [])
        combined = _joined_content(messages)
        assert s["variantId"] in combined, (
            f"Compiled messages for selection {s.get('iteration')} must contain the "
            f"variant id token '{s['variantId']}'."
        )
        assert CUSTOMER_NAME in combined, (
            "Compiled messages must contain the substituted customer_name 'Dana Lopez'."
        )
        assert QUESTION in combined, (
            "Compiled messages must contain the substituted question value."
        )
        assert "{{" not in combined, (
            "Compiled messages must not contain any unresolved '{{' placeholders."
        )


# ---------------------------------------------------------------------------
# Step 3: Span log records the chosen variant on the trace.
# ---------------------------------------------------------------------------
def test_span_log_records_selected_variant(main_run):
    data, spans = main_run
    prompt_spans = [sp for sp in spans if _span_type_is_prompt(sp)]
    assert len(prompt_spans) >= 3000, (
        f"Expected at least 3000 prompt spans in the span log, got {len(prompt_spans)}."
    )

    span_by_id = {}
    span_variant_tally = {}
    for sp in prompt_spans:
        sid = _span_id(sp)
        vid = _span_variant_id(sp)
        if sid is not None:
            span_by_id[sid] = sp
        if vid is not None:
            span_variant_tally[vid] = span_variant_tally.get(vid, 0) + 1

    for s in data.get("selections", []):
        sid = str(s.get("spanId"))
        assert sid in span_by_id, (
            f"Selection {s.get('iteration')} spanId {sid} not found among exported prompt spans."
        )
        sp = span_by_id[sid]
        assert _span_variant_id(sp) == s["variantId"], (
            f"Span {sid} recorded variant "
            f"'{_span_variant_id(sp)}' but the selection chose '{s['variantId']}'."
        )
        assert _span_handle(sp) == VARIANTS[s["variantId"]], (
            f"Span {sid} must record handle '{VARIANTS[s['variantId']]}'."
        )
        assert _span_version_is_int(sp), (
            f"Span {sid} must record an integer prompt version."
        )

    distribution = data.get("distribution", {})
    for vid in VARIANTS:
        assert span_variant_tally.get(vid, 0) == distribution.get(vid, 0), (
            f"Span-log variant tally for '{vid}' ({span_variant_tally.get(vid, 0)}) "
            f"does not match the summary distribution ({distribution.get(vid, 0)})."
        )


# ---------------------------------------------------------------------------
# Step 4: Deterministic reproducibility (same seed).
# ---------------------------------------------------------------------------
def test_same_seed_is_deterministic():
    out_a, spans_a = "/tmp/ab_out_a.json", "/tmp/ab_spans_a.jsonl"
    out_b, spans_b = "/tmp/ab_out_b.json", "/tmp/ab_spans_b.jsonl"
    _cleanup(out_a, spans_a, out_b, spans_b)

    r1 = _run_switch(200, 42, FULL_VARS, out_a, spans_a)
    assert r1.returncode == 0, f"First seed-42 run failed.\nSTDERR:\n{r1.stderr}"
    r2 = _run_switch(200, 42, FULL_VARS, out_b, spans_b)
    assert r2.returncode == 0, f"Second seed-42 run failed.\nSTDERR:\n{r2.stderr}"

    seq_a = [s["variantId"] for s in _load_json_file(out_a).get("selections", [])]
    seq_b = [s["variantId"] for s in _load_json_file(out_b).get("selections", [])]
    assert len(seq_a) == 200 and len(seq_b) == 200, (
        "Both seed-42 runs must produce 200 selections."
    )
    assert seq_a == seq_b, (
        "Two runs with the same seed must produce identical ordered variant sequences."
    )


# ---------------------------------------------------------------------------
# Step 5: Different seed changes the sequence.
# ---------------------------------------------------------------------------
def test_different_seed_changes_sequence():
    out_seed42, spans_seed42 = "/tmp/ab_out_a.json", "/tmp/ab_spans_a.jsonl"
    out_c, spans_c = "/tmp/ab_out_c.json", "/tmp/ab_spans_c.jsonl"
    _cleanup(out_seed42, spans_seed42, out_c, spans_c)

    r42 = _run_switch(200, 42, FULL_VARS, out_seed42, spans_seed42)
    assert r42.returncode == 0, f"Seed-42 run failed.\nSTDERR:\n{r42.stderr}"
    r99 = _run_switch(200, 99, FULL_VARS, out_c, spans_c)
    assert r99.returncode == 0, f"Seed-99 run failed.\nSTDERR:\n{r99.stderr}"

    seq42 = [s["variantId"] for s in _load_json_file(out_seed42).get("selections", [])]
    seq99 = [s["variantId"] for s in _load_json_file(out_c).get("selections", [])]
    assert seq42 != seq99, (
        "Runs with different seeds should not produce identical variant sequences."
    )


# ---------------------------------------------------------------------------
# Step 6: Missing required variable fails.
# ---------------------------------------------------------------------------
def test_missing_required_variable_fails():
    out_bad, spans_bad = "/tmp/ab_out_bad.json", "/tmp/ab_spans_bad.jsonl"
    _cleanup(out_bad, spans_bad)
    result = _run_switch(5, 7, MISSING_VARS, out_bad, spans_bad)
    assert result.returncode != 0, (
        "Running with a missing required variable ('question') must exit non-zero, "
        f"but it succeeded.\nSTDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}"
    )
    if os.path.isfile(out_bad):
        try:
            data = _load_json_file(out_bad)
        except json.JSONDecodeError:
            return
        selections = data.get("selections", [])
        if len(selections) == 5:
            for s in selections:
                combined = _joined_content(s.get("messages", []))
                assert "{{" in combined or QUESTION not in combined, (
                    "A fully compiled successful summary must not be produced when a "
                    "required variable is missing."
                )
