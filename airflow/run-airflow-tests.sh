#!/usr/bin/env bash
# 1) DagBag integrity tests in apache/airflow. 2) a real `airflow dags test` run of
# one logical date against a throwaway Postgres (runs the tasks end-to-end, twice,
# to prove the partition load is idempotent).
set -euo pipefail
cd "$(dirname "$0")/.."
IMG=apache/airflow:2.10.5-python3.12
NET=misc3-af; docker network create $NET >/dev/null 2>&1 || true
docker rm -f misc3-af-pg >/dev/null 2>&1 || true
docker run -d --name misc3-af-pg --network $NET -e POSTGRES_USER=receipts -e POSTGRES_PASSWORD=receipts -e POSTGRES_DB=receipts postgres:16-alpine >/dev/null
trap 'docker rm -f misc3-af-pg >/dev/null; docker network rm $NET >/dev/null' EXIT
[ -f data/receipts.csv ] || python3 -m receipts.generate data/receipts.csv
docker run --rm --network $NET -v "$PWD/airflow/dags":/opt/airflow/dags -v "$PWD/airflow":/opt/airflow/tests \
  -v "$PWD/receipts":/opt/airflow/receipts -v "$PWD/data":/opt/airflow/data \
  -e PYTHONPATH=/opt/airflow -e PG_DSN=postgresql://receipts:receipts@misc3-af-pg:5432/receipts \
  -e AIRFLOW__CORE__LOAD_EXAMPLES=False --entrypoint bash $IMG -c '
  set -e
  airflow db migrate >/dev/null
  pip install -q pytest 2>&1 | tail -1
  python -m pytest -q -p no:cacheprovider /opt/airflow/tests/test_dag_integrity.py
  for i in 1 2; do airflow dags test receipts_etl 2026-09-03 2>&1 | grep -E "partition 2026-09-03|state=|Marking run" | tail -3; done
  python - <<PY
import psycopg2
c = psycopg2.connect("postgresql://receipts:receipts@misc3-af-pg:5432/receipts").cursor()
c.execute("select count(*) from receipts"); print("rows in receipts after two runs of 2026-09-03:", c.fetchone()[0])
PY'
