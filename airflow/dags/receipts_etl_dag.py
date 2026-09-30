"""Daily receipts ETL.

- schedule: @daily, catchup allowed so missed days are backfilled
- retries: 3 with exponential backoff (transient Postgres/network errors)
- idempotent partitions: each run (re)loads ONLY its logical date {{ ds }}
  (delete-then-insert in one transaction), so a retry or a manual re-run of a
  day never double counts and never touches other days.
- max_active_runs=1 keeps backfills from racing on the quarantine table.
"""
from datetime import date, datetime, timedelta
import os

from airflow import DAG
from airflow.operators.python import PythonOperator, ShortCircuitOperator

RAW = os.environ.get("RECEIPTS_CSV", "/opt/airflow/data/receipts.csv")
DSN = os.environ.get("PG_DSN", "postgresql://receipts:receipts@postgres:5432/receipts")


def has_input(**_):
    return os.path.exists(RAW)


def load_partition(ds, **_):
    from receipts.etl import run
    loaded, quarantined = run(RAW, DSN, business_date=date.fromisoformat(ds))
    print(f"partition {ds}: loaded={loaded} quarantined_total={quarantined}")
    return loaded


def check_partition(ds, **_):
    import psycopg2
    with psycopg2.connect(DSN) as c, c.cursor() as cur:
        cur.execute("SELECT count(*), count(DISTINCT receipt_id) FROM receipts WHERE business_date=%s", (ds,))
        n, distinct = cur.fetchone()
    if n != distinct:
        raise ValueError(f"duplicate receipts in partition {ds}")
    print(f"partition {ds}: {n} rows ok")


with DAG(
    dag_id="receipts_etl",
    start_date=datetime(2026, 9, 1),
    schedule="@daily",
    catchup=True,
    max_active_runs=1,
    default_args={"owner": "misc-lab-3", "retries": 3, "retry_delay": timedelta(minutes=2),
                  "retry_exponential_backoff": True},
    tags=["receipts", "etl"],
) as dag:
    wait = ShortCircuitOperator(task_id="input_available", python_callable=has_input)
    load = PythonOperator(task_id="load_partition", python_callable=load_partition)
    check = PythonOperator(task_id="check_partition", python_callable=check_partition)
    wait >> load >> check
