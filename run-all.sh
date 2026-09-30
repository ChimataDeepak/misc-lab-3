#!/usr/bin/env bash
# Runs every verification in this lab. Needs Docker (Postgres/Airflow/Hadoop) and Java 17+ (Spark).
set -euo pipefail
cd "$(dirname "$0")"
[ -d .venv ] || { python3 -m venv .venv && .venv/bin/pip install -q -r requirements.txt; }
export TESTCONTAINERS_RYUK_DISABLED=${TESTCONTAINERS_RYUK_DISABLED:-true}
.venv/bin/python -m receipts.generate data/receipts.csv
echo "== pytest: ETL, Spark, ML, RAG, Hadoop mapper/reducer =="; .venv/bin/pytest -q tests
echo "== Airflow DAG integrity + dags test ==";                  ./airflow/run-airflow-tests.sh
echo "== Hadoop Streaming in apache/hadoop ==";                  ./hadoop/run-streaming.sh data/receipts.csv
echo "== Fraud model metrics ==";                                .venv/bin/python -m ml.fraud
if [ -n "${RUN_OLLAMA:-}" ]; then echo "== RAG against Ollama =="; .venv/bin/pytest -q -s tests/test_rag.py -k ollama; fi
