from datetime import datetime
import pytest

pyspark = pytest.importorskip("pyspark")
from spark.daily_spend import spark_session, daily_totals, rolling_7d


@pytest.fixture(scope="module")
def spark():
    s = spark_session("test")
    yield s
    s.stop()


def fixture_df(spark):
    rows = [  # payer, currency, amount, amount_inr, ts
        ("a", "EUR", 10.0, 901.0, datetime(2026, 9, 1, 10)),
        ("a", "EUR", 5.0, 450.5, datetime(2026, 9, 1, 18)),
        ("a", "EUR", 20.0, 1802.0, datetime(2026, 9, 5, 9)),
        ("a", "EUR", 1.0, 90.1, datetime(2026, 9, 9, 9)),   # 9-01 falls out of the 7-day window
        ("b", "INR", 100.0, 100.0, datetime(2026, 9, 1, 12)),
    ]
    return spark.createDataFrame(rows, "payer string, currency string, amount double, amount_inr double, ts timestamp")


def test_daily_totals_by_currency_and_payer(spark):
    out = {(str(r.business_date), r.currency, r.payer): (r.total, r.n) for r in daily_totals(fixture_df(spark)).collect()}
    assert out[("2026-09-01", "EUR", "a")] == (15.0, 2)
    assert out[("2026-09-01", "INR", "b")] == (100.0, 1)
    assert len(out) == 4


def test_rolling_7_day_window_is_range_based(spark):
    out = {(r.payer, str(r.business_date)): r.rolling_7d_inr for r in rolling_7d(fixture_df(spark)).collect()}
    assert out[("a", "2026-09-01")] == 1351.5
    assert out[("a", "2026-09-05")] == 3153.5            # 9-01 + 9-05
    assert out[("a", "2026-09-09")] == 1892.1            # 9-03..9-09 -> only 9-05 + 9-09
    assert out[("b", "2026-09-01")] == 100.0
