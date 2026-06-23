LangWatch supports fetching offline datasets and executing server-side managed evaluation loops on historical data to compare model or pipeline performance.

You need to write a Python script that fetches the `dataset-customer-queries` dataset via LangWatch, initializes an evaluation run named `rag-accuracy-experiment`, and iterates over the dataset to execute a RAG pipeline.

**Constraints:**
- You must use `evaluation.loop()` to iterate over the pandas dataframe converted from the dataset.
- Inside the loop, you must execute the built-in `legacy/ragas_context_utilization` evaluator.
- You must properly map the `input`, `output` (from your mock pipeline), and `contexts` fields into the evaluator's data payload.