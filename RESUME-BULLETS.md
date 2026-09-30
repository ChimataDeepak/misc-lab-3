# Resume bullets (misc-lab-3), verified items only

- Built a Python ETL pipeline for payment receipts into PostgreSQL with row validation, a quarantine table for bad rows, dedupe on business key and Decimal currency normalisation; idempotent per-date loads, tested with pytest + Testcontainers.
- Orchestrated the ETL with an Apache Airflow DAG (daily schedule, retries with exponential backoff, per-partition reloads); verified with DagBag tests and repeated `airflow dags test` runs in the official Docker image.
- Wrote PySpark jobs for daily spend by currency and payer and a range-based rolling 7-day window; unit tested in local mode.
- Implemented a Hadoop Streaming MapReduce job (receipts and totals per currency, bad-row counters), run in the apache/hadoop Docker image.
- Trained a scikit-learn fraud classifier on synthetic receipts with leakage-free, point-in-time features (precision 0.90, recall 0.95 on injected fraud patterns) and served it through a validated FastAPI /score endpoint.
- Built retrieval-augmented Q&A over receipts (embeddings, cosine retrieval, OpenAI-compatible client) where totals are computed from data and the LLM only phrases them, with a hallucination guard; tested with a deterministic stub and against a local Ollama model (qwen2.5 0.5B) in Docker.

Wording rule: "synthetic data", "tested locally / in containers". Never "production".
