# LEARN: Apache Airflow

## What
A scheduler for batch workflows: DAGs (directed acyclic graphs) of tasks, run per logical date, with retries and backfill.

## Why it exists
Cron runs a script; it doesn't know that Tuesday failed, can't backfill last month, and can't say "B runs only after A
succeeded". Airflow tracks every (DAG, logical date, task) attempt.

## How it works
```
receipts_etl  (@daily, start 2026-09-01, catchup=True, max_active_runs=1)

  input_available  ---->  load_partition(ds)  ---->  check_partition(ds)
  ShortCircuitOperator    PythonOperator              PythonOperator
  (skip if CSV missing)   etl.run(business_date=ds)   count == count(distinct)
  retries=3, retry_delay=2 min, exponential backoff on every task
```
- `ds` is the logical date the run is for, not "now". Re-running 2026-09-03 always reloads 2026-09-03.
- `catchup=True` creates runs for every missed day since `start_date` (backfill).

## Where in this repo
- DAG: `airflow/dags/receipts_etl_dag.py:41-54`; retries at lines 47-48; `max_active_runs` line 46.
- Tasks: `has_input` line 20, `load_partition` line 24 (calls `receipts.etl.run`), `check_partition` line 31.
- Integrity tests: `airflow/test_dag_integrity.py` (import errors, task order, retries, schedule).
- Runner: `airflow/run-airflow-tests.sh` (official `apache/airflow:2.10.5-python3.12` image + throwaway Postgres).

## How it's verified
`./airflow/run-airflow-tests.sh` on 2026-09-30 (RUN-RESULTS.md): DagBag tests 4 passed; `airflow dags test receipts_etl
2026-09-03` run twice, both `state=success`, 115 rows in the table after both runs (idempotent).
Not run: a long-running scheduler + webserver; `dags test` executes the real tasks in-process.

## Interview Q&A
- **Q: What makes a task safe to retry?** Idempotency keyed on the logical date: the same inputs produce the same
  partition, so retry = overwrite.
- **Q: `catchup` vs `backfill`?** `catchup` auto-creates missed runs when the DAG is unpaused; `airflow dags backfill`
  runs a chosen range on demand.
- **Q: Why keep logic out of the DAG file?** The scheduler parses DAG files constantly; heavy imports slow it down and
  logic inside operators is hard to test. Here the import is inside the callable (line 25).
- **Q: Why `max_active_runs=1`?** Backfill runs would race on shared state (the quarantine table).
- **Q: Sensor vs ShortCircuit?** A sensor waits for the file; ShortCircuit skips downstream if it's absent now.

## Try it yourself
1. Replace `ShortCircuitOperator` with a `FileSensor` (`mode="reschedule"`, timeout 1 h) and explain the worker-slot
   difference between `poke` and `reschedule`.
2. Add an SLA / `on_failure_callback` that logs the failed `ds`.
3. Backfill three days with `airflow dags backfill -s 2026-09-01 -e 2026-09-03 receipts_etl` in the container and count
   rows per `business_date`.
