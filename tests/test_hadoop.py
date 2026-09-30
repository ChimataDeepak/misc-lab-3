"""Checks the awk mapper/reducer locally with the same map|sort|reduce contract
Hadoop Streaming uses, and cross-checks against the Python ETL's counts.
(Note: the ETL dedupes; MapReduce counts raw lines, so duplicates are included.)"""
import os, shutil, subprocess
from collections import Counter
import pytest
from receipts.generate import generate, write_csv

HERE = os.path.join(os.path.dirname(__file__), "..", "hadoop")


@pytest.mark.skipif(not shutil.which("awk"), reason="awk missing")
def test_map_sort_reduce_counts_receipts_per_currency(tmp_path):
    rows = generate()
    p = tmp_path / "r.csv"
    write_csv(p, rows)
    cmd = f"awk -f {HERE}/mapper.awk {p} 2>/dev/null | LC_ALL=C sort | awk -f {HERE}/reducer.awk"
    out = subprocess.run(cmd, shell=True, capture_output=True, text=True, check=True).stdout
    got = {l.split("\t")[0]: int(l.split("\t")[1]) for l in out.strip().splitlines()}
    expected = Counter(r["currency"] for r in rows
                       if r["currency"] in {"INR", "USD", "EUR", "GBP"} and r["amount"].replace(".", "").isdigit()
                       and float(r["amount"]) > 0)
    assert got == dict(expected)
    assert sum(got.values()) == len(rows) - 3  # BAD1 negative, BAD2 XYZ, BAD3 abc
