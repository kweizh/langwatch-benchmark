# LangWatch Evaluation Dataset CSV Round-Trip Pipeline

## Background
LangWatch offline experiments load their evaluation datasets from CSV files and export experiment results back to CSV (e.g. via `pandas.read_csv(...)` and the "Export to CSV" workflow). A LangWatch evaluation dataset row typically contains an `input`/`question`, an `expected_output`, plus nested columns such as `contexts` (the list of retrieved RAG documents) and `conversation_history` (a multi-turn chat transcript). These nested columns are serialized into a single CSV cell.

When a single retrieved-context blob or a long conversation history is serialized, one CSV cell can easily exceed 131072 characters. Python's standard `csv` module enforces a default per-field size limit of 131072 characters, so a naive reader will crash while parsing such an export with:

```
_csv.Error: field larger than field limit (131072)
```

You must build a robust import/export pipeline that survives these oversized fields and round-trips the dataset without any truncation or corruption.

## Requirements
Build a Python command-line pipeline named `pipeline.py` that provides two subcommands, `export` and `import`, operating on LangWatch-style evaluation dataset records.

The canonical in-memory/JSON record shape is a JSON array of objects, each with exactly these fields:
- `index`: integer row number (0-based)
- `question`: string
- `expected_output`: string
- `contexts`: array of strings (retrieved RAG documents)
- `conversation_history`: array of objects, each `{"role": string, "content": string}`

- `export`: read the records from an input JSON file and write them to a CSV file. The CSV must have a header row with exactly these columns in this order: `index,question,expected_output,contexts,conversation_history`. The two nested columns (`contexts`, `conversation_history`) must be stored as compact JSON (`json.dumps(value, ensure_ascii=False, separators=(",", ":"))`) inside a single CSV cell. The pipeline must correctly quote/escape cells that contain commas, double quotes, and embedded newlines.
- `import`: read the CSV file produced by `export` (which may contain individual fields far larger than 131072 characters) and reconstruct the exact original records into an output JSON file. The two nested columns must be JSON-decoded back into their native list/object form, and `index` must be restored as an integer. Parsing must not fail on oversized fields and must not truncate or corrupt any content.

Both subcommands must also emit a machine-readable report.

## Implementation Hints
- The LangWatch/Python `csv` module reader raises `_csv.Error: field larger than field limit (131072)` on oversized cells. You need to raise `csv.field_size_limit(...)` high enough before parsing. Note that passing an excessively large value (e.g. `sys.maxsize`) can raise `OverflowError: Python int too large to convert to C long` on some platforms, so handle that gracefully.
- Keep the write/read symmetric: whatever quoting dialect you use for `export` must be readable by `import`. Use a consistent, standard CSV dialect.
- Preserve nested structures losslessly by encoding them as JSON in the cell, then decoding on the way back. Do not depend on `str()`/`repr()` of Python objects.
- Install the `langwatch` SDK with `uv` (LangWatch datasets are pandas-backed; `pandas` is available for reading/writing frames if you choose to use it). Never mock any dependency; read any secrets you need from environment variables.
- The report is printed to stdout, but stdout may also contain SDK/log noise. Emit the report on its own final line prefixed with a stable marker so it can be reliably extracted.

## Acceptance Criteria
- Project path: /home/user/langwatch-csv-pipeline
- Command (export): `python pipeline.py export --input <records.json> --output <dataset.csv>`
- Command (import): `python pipeline.py import --input <dataset.csv> --output <records.json>`
- `export` writes a CSV whose first line is exactly the header `index,question,expected_output,contexts,conversation_history` and whose `contexts`/`conversation_history` cells contain compact JSON of the corresponding list values.
- `import` writes an output JSON file that is a JSON array of record objects with the fields `index` (integer), `question` (string), `expected_output` (string), `contexts` (array of strings), and `conversation_history` (array of `{role, content}` objects).
- Round-trip integrity: for any input dataset, running `export` and then `import` on the resulting CSV MUST reproduce the original records exactly (same order, same field values, no truncation), including records whose serialized `contexts` or `conversation_history` cell exceeds 131072 characters and cells containing commas, double quotes, and newlines.
- Both subcommands print, as the final stdout line, a report prefixed with the exact marker `LANGWATCH_CSV_REPORT ` followed by a single compact JSON object with the fields:
  - `operation`: either `"export"` or `"import"`
  - `record_count`: integer number of records processed
  - `max_field_chars`: integer character length of the longest individual CSV field value in the dataset
  - `field_size_limit`: integer CSV field size limit the pipeline set (must be greater than `max_field_chars`)
  - `checksums`: object mapping each record's `index` (as a string) to an object `{"contexts": <sha256hex>, "conversation_history": <sha256hex>}`, where each hash is the SHA-256 hex digest of the UTF-8 bytes of the compact JSON (`json.dumps(value, ensure_ascii=False, separators=(",", ":"))`) of that field's value.
- The pipeline must exit with status code 0 on success.

