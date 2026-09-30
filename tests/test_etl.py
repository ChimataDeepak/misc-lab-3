from datetime import date
import pytest
from receipts.generate import generate
from receipts.etl import transform, validate, load


def test_generator_is_deterministic():
    assert generate(seed=7)[:50] == generate(seed=7)[:50]


def test_bad_rows_quarantined_with_reasons():
    clean, q = transform(generate())
    reasons = {rid: reason for rid, _, reason in q}
    assert reasons["BAD1"] == "amount not positive"
    assert reasons["BAD2"] == "unknown currency XYZ"
    assert reasons["BAD3"] == "amount not numeric"
    assert reasons["BAD4"] == "bad timestamp"
    assert reasons["BAD5"] == "missing payer"
    assert len(q) == 5


def test_duplicates_removed():
    rows = generate()
    clean, _ = transform(rows)
    ids = [c["receipt_id"] for c in clean]
    assert len(ids) == len(set(ids))
    assert len(clean) == len(rows) - 15 - 5


def test_currency_normalised_to_inr():
    c, _ = validate({"receipt_id": "x", "payer": "p", "merchant": "m", "amount": "10.00",
                     "currency": "usd", "ts": "2026-09-02T10:00:00", "is_fraud": "0"})
    assert str(c["amount_inr"]) == "832.00" and c["currency"] == "USD"


@pytest.fixture(scope="module")
def pg():
    tc = pytest.importorskip("testcontainers.postgres")
    import psycopg2
    with tc.PostgresContainer("postgres:16-alpine", driver=None) as p:
        conn = psycopg2.connect(p.get_connection_url())
        yield conn
        conn.close()


def count(conn, sql, *a):
    with conn.cursor() as c:
        c.execute(sql, a)
        return c.fetchone()[0]


def test_load_into_postgres_and_rerun_is_idempotent(pg):
    clean, q = transform(generate())
    load(pg, clean, q)
    n1 = count(pg, "SELECT count(*) FROM receipts")
    load(pg, clean, q)  # retry of the same run
    assert count(pg, "SELECT count(*) FROM receipts") == n1 == len(clean)
    assert count(pg, "SELECT count(*) FROM receipts_quarantine") == 5


def test_single_partition_reload_touches_only_that_day(pg):
    clean, q = transform(generate())
    load(pg, clean, q)
    d = date(2026, 9, 3)
    before_other = count(pg, "SELECT count(*) FROM receipts WHERE business_date<>%s", d)
    load(pg, clean, q, business_date=d)
    load(pg, clean, q, business_date=d)
    assert count(pg, "SELECT count(*) FROM receipts WHERE business_date<>%s", d) == before_other
    assert count(pg, "SELECT count(*) FROM receipts WHERE business_date=%s", d) == \
        sum(1 for c in clean if c["business_date"] == d)
