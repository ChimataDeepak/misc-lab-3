"""DAG integrity tests: run inside the official apache/airflow image (see Makefile)."""
from datetime import timedelta
from airflow.models import DagBag


def bag():
    return DagBag(dag_folder="/opt/airflow/dags", include_examples=False)


def test_no_import_errors():
    assert bag().import_errors == {}


def test_receipts_dag_shape():
    dag = bag().get_dag("receipts_etl")
    assert dag is not None
    assert [t.task_id for t in dag.topological_sort()] == ["input_available", "load_partition", "check_partition"]
    assert dag.max_active_runs == 1 and dag.catchup


def test_retries_configured_on_every_task():
    for t in bag().get_dag("receipts_etl").tasks:
        assert t.retries == 3 and t.retry_delay == timedelta(minutes=2) and t.retry_exponential_backoff


def test_daily_schedule():
    assert str(bag().get_dag("receipts_etl").timetable.summary) in ("@daily", "0 0 * * *")
