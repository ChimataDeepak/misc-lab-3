# Run results

Machine: macOS arm64 (Apple Silicon), Rancher Desktop Docker, Python 3.13.5 venv, Corretto 21.
Data: `receipts/generate.py` seed 42 → 3,145 rows (3,125 unique valid, 15 duplicates, 5 bad; 4.0% fraud).
All data is synthetic.

| Date | Area | Command | Result |
|---|---|---|---|
| 2026-09-30 | ETL + PostgreSQL | `pytest -q tests/test_etl.py` (Testcontainers `postgres:16-alpine`, `TESTCONTAINERS_RYUK_DISABLED=true`) | 6 passed |
| 2026-09-30 | Spark | `pytest -q tests/test_spark.py` (PySpark 4.2.0, local[2], Java 21) | 2 passed |
| 2026-09-30 | ML + FastAPI | `pytest -q tests/test_ml.py` | 6 passed |
| 2026-09-30 | ML metrics | `python -m ml.fraud` | n_train 2187, n_test 938, precision 0.90, recall 0.9474, ROC-AUC 0.9998 |
| 2026-09-30 | RAG (stub) | `pytest -q tests/test_rag.py` | 6 passed, 1 skipped (Ollama test) |
| 2026-09-30 | RAG (real Ollama) | `RUN_OLLAMA=1 pytest -q -s tests/test_rag.py -k ollama` (ollama/ollama in Docker, `qwen2.5:0.5b` chat, `nomic-embed-text` 768-d embeddings, CPU) | 1 passed; answer "payer_055 spent 533.20 EUR across 14 receipts between 2026-09-15 and 2026-09-21.", LLM answer contained the computed total (guard not triggered) |
| 2026-09-30 | Hadoop mapper/reducer | `pytest -q tests/test_hadoop.py` | 1 passed |
| 2026-09-30 | Full local suite | `pytest -q tests` | 21 passed, 1 skipped |
| 2026-09-30 | Airflow | `./airflow/run-airflow-tests.sh` (`apache/airflow:2.10.5-python3.12`, SQLite metadata DB, Postgres target) | DagBag tests 4 passed; `airflow dags test receipts_etl 2026-09-03` run twice → both `state=success`, 115 rows in the partition after both runs (idempotent) |
| 2026-09-30 | Hadoop Streaming | `./hadoop/run-streaming.sh data/receipts.csv` (`apache/hadoop:3.4.1`, amd64 image under emulation, local job runner) | EUR 855 / GBP 481 / INR 1046 / USD 760 = 3,142 lines; counter bad_rows=3 |

Not run: GitHub Actions (branch is not pushed). Airflow was verified with `airflow dags test`
(runs real tasks in-process) rather than a long-running scheduler + webserver.
Hadoop ran in a single container with the local job runner, not a multi-node HDFS/YARN cluster.

## Independent re-verification (2026-09-30)
Re-ran everything: ETL 6 passed (alone; 2 Testcontainers setup errors when run inside the full suite under load, pass on rerun), Spark/ML/RAG-stub/Hadoop-local passed,
Airflow DagBag 4 passed + 2x `dags test` success with 115 rows, Hadoop Streaming counts identical, ML metrics identical,
real Ollama test 1 passed (failed once with an HTTP error on a cold model, passed on rerun).
