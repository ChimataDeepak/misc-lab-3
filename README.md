# misc-lab-3: receipts data & ML platform

A small, end-to-end data platform over **synthetic** receipt/payment data.
`receipts/generate.py` produces ~3.1k receipts deterministically (seed 42) for 60 payers in
INR/USD/EUR/GBP, with three injected fraud patterns (card-testing bursts, large foreign-currency
spends, high-value night purchases), 15 duplicate deliveries and 5 deliberately bad rows.

```
generate.py ──► ETL (validate, dedupe, FX→INR) ──► PostgreSQL ◄── Airflow DAG (@daily, per-partition)
     │                       │
     ├──► Hadoop Streaming (receipts per currency)
     ├──► PySpark (daily totals, rolling 7-day spend)
     └──► scikit-learn fraud model ──► FastAPI /score
                             └──► RAG Q&A (embeddings + retrieval + LLM phrasing, Ollama or stub)
```

Run everything: `./run-all.sh` (or `make all`). Results of the last run: [RUN-RESULTS.md](RUN-RESULTS.md).

## Skills table

| Skill | Where | What it really does | Verified by |
|---|---|---|---|
| ETL / data pipeline (Python, PostgreSQL) | `receipts/etl.py` | validation → quarantine table with reason, dedupe on `receipt_id`, Decimal FX normalisation to INR, idempotent delete+insert per business date in one transaction | `tests/test_etl.py` (Postgres via Testcontainers) |
| Airflow | `airflow/dags/receipts_etl_dag.py` | `@daily`, catchup, `max_active_runs=1`, 3 retries with exponential backoff, each run reloads only `{{ ds }}` | DagBag tests + two real `airflow dags test` runs in `apache/airflow:2.10.5` |
| Spark | `spark/daily_spend.py` | local-mode PySpark: daily totals by date×currency×payer, **range**-based 7-day rolling window | `tests/test_spark.py` |
| Hadoop | `hadoop/*.awk`, `run-streaming.sh` | Hadoop Streaming MapReduce counting receipts + totals per currency, bad rows via a Hadoop counter | real job in `apache/hadoop:3.4.1` (amd64 image, emulated on arm64) + local map/sort/reduce test |
| Machine learning | `ml/fraud.py` | point-in-time features (burst, foreign currency, amount vs payer median, night), RandomForest, stratified split, precision/recall/ROC-AUC, joblib persistence | `tests/test_ml.py` |
| Model serving (FastAPI) | `ml/api.py` | `/score` with pydantic validation (422), 503 when the model is absent | `tests/test_ml.py` |
| LLM / GenAI (RAG) | `rag/` | OpenAI-compatible client (Ollama `/v1`), embeddings + cosine retrieval, LLM phrases computed facts, hallucination guard | `tests/test_rag.py` (stub) + optional Ollama run |
| CI / infra | `.github/workflows/ci.yml`, `docker-compose.yml`, `Makefile` | three CI jobs; compose for Postgres, scorer, optional Ollama | CI config only (not run on GitHub: branch not pushed) |

**Data honesty:** everything is synthetic. The fraud model's near-perfect ROC-AUC shows the
features recover patterns *I injected*; it says nothing about real-world fraud performance.

## Real vs simulated

| Part | Real | Simulated / not run |
|---|---|---|
| Data | - | All receipts are synthetic (`receipts/generate.py`, seed 42); fraud patterns, duplicates and bad rows are injected |
| PostgreSQL | Real Postgres 16 (Testcontainers in tests, compose locally) | - |
| Airflow | Official `apache/airflow:2.10.5` image, real tasks via `airflow dags test` twice | No long-running scheduler or webserver |
| Spark | Real PySpark 4.2 | `local[2]` on one machine, no cluster |
| Hadoop | Real Hadoop 3.4.1 Streaming job | Local job runner in one container (no HDFS/YARN cluster), amd64 image under emulation on arm64 |
| ML | Real scikit-learn training and FastAPI serving | Metrics are on synthetic, injected patterns; random (not time-based) split |
| RAG / LLM | Real Ollama run once (`qwen2.5:0.5b`, `nomic-embed-text`) | Default tests use a deterministic stub client; no hosted LLM, no vector DB |
| CI | Workflow file exists | Never run on GitHub (branch not pushed) |

Architecture, failure modes and decisions: [ARCHITECTURE.md](ARCHITECTURE.md). Per-skill notes: `learn/LEARN-*.md`.

## How I'd explain it in an interview

**ETL.** "Bad rows shouldn't kill a batch, and good rows shouldn't be silently lost. Each row is
validated; failures go to a quarantine table with a reason so ops can fix and replay. Dedupe is on
the business key because upstreams redeliver. Money is `Decimal`, never float. The load is
delete-then-insert of a partition inside one transaction, so a retry is idempotent."

**Airflow.** "The DAG is thin: orchestration, not logic. The logic is a plain function I unit test
outside Airflow. Idempotency comes from the task being keyed on the logical date, so retries and
backfills are safe; I proved it by running the same date twice and getting the same row count.
The DagBag test catches import errors and cycles before deploy."

**Spark.** "For 'rolling 7 days' I use a *range* window over the date, not `rowsBetween(-6,0)` —
rows means '7 records', which is wrong when a payer skips days. The test has a gap on purpose."

**Hadoop.** "Streaming lets any executable be the mapper/reducer; the contract is stdin/stdout and
the framework sorts by key between them. The image has no Python, so I wrote them in awk. The
reducer relies on sorted input — the local test reproduces that with `sort`. On an M-series Mac
the image is amd64-only and ran under emulation."

**ML.** "The key risk is leakage: every feature is computed from the payer's history *before* the
current receipt, in timestamp order, so the model never sees the future. Class imbalance (~4%
fraud) is handled with `class_weight='balanced'` and I report precision/recall, not accuracy.
Serving validates inputs and fails closed (503) if the model file isn't there."

**RAG.** "An LLM is bad at arithmetic, so it never computes money. I parse the question to a
structured query, compute the exact total from the data, retrieve the top receipts by embedding
similarity as citations, and the LLM only phrases the answer. A guard checks the computed figure
appears in the answer and falls back to a template if it doesn't. The client speaks the OpenAI
API, so Ollama locally or a hosted model is a config change; tests use a deterministic stub."
