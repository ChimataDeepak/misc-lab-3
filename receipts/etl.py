"""Extract -> transform -> load for receipts.

Transform: validate (schema, positive amount, known currency, parseable ts,
non-empty payer), dedupe on receipt_id, normalise every amount to INR using a
fixed daily rate table. Invalid rows go to a quarantine table with a reason
instead of failing the whole batch.

Load is idempotent per partition (business date): the partition is deleted
and re-inserted in one transaction, so a retried run never double counts.
"""
import csv
from datetime import datetime
from decimal import Decimal, InvalidOperation

RATES_TO_INR = {"INR": Decimal("1"), "USD": Decimal("83.20"), "EUR": Decimal("90.10"), "GBP": Decimal("105.40")}

DDL = """
CREATE TABLE IF NOT EXISTS receipts (
  receipt_id TEXT PRIMARY KEY, payer TEXT NOT NULL, merchant TEXT NOT NULL,
  amount NUMERIC(14,2) NOT NULL, currency CHAR(3) NOT NULL,
  amount_inr NUMERIC(16,2) NOT NULL, ts TIMESTAMP NOT NULL,
  business_date DATE NOT NULL, is_fraud BOOLEAN NOT NULL);
CREATE INDEX IF NOT EXISTS receipts_bd ON receipts(business_date);
CREATE TABLE IF NOT EXISTS receipts_quarantine (
  receipt_id TEXT, raw TEXT NOT NULL, reason TEXT NOT NULL,
  business_date DATE, loaded_at TIMESTAMP DEFAULT now());
"""


def extract(path):
    with open(path, newline="") as f:
        return list(csv.DictReader(f))


def validate(row):
    """Return (clean_row, None) or (None, reason)."""
    if not row.get("receipt_id"):
        return None, "missing receipt_id"
    if not row.get("payer"):
        return None, "missing payer"
    try:
        amount = Decimal(row["amount"])
    except (InvalidOperation, TypeError):
        return None, "amount not numeric"
    if amount <= 0:
        return None, "amount not positive"
    cur = (row.get("currency") or "").upper()
    if cur not in RATES_TO_INR:
        return None, f"unknown currency {cur}"
    try:
        ts = datetime.fromisoformat(row["ts"])
    except (ValueError, TypeError):
        return None, "bad timestamp"
    return {"receipt_id": row["receipt_id"], "payer": row["payer"], "merchant": row.get("merchant") or "unknown",
            "amount": amount, "currency": cur,
            "amount_inr": (amount * RATES_TO_INR[cur]).quantize(Decimal("0.01")),
            "ts": ts, "business_date": ts.date(),
            "is_fraud": str(row.get("is_fraud", "0")) in ("1", "true", "True")}, None


def transform(rows):
    clean, quarantine, seen = [], [], set()
    for r in rows:
        c, reason = validate(r)
        if reason:
            quarantine.append((r.get("receipt_id"), r, reason))
        elif c["receipt_id"] in seen:
            continue  # duplicate delivery: drop silently, first wins
        else:
            seen.add(c["receipt_id"])
            clean.append(c)
    return clean, quarantine


def load(conn, clean, quarantine, business_date=None):
    """Idempotent load. If business_date is given, only that partition is (re)loaded."""
    if business_date is not None:
        clean = [c for c in clean if c["business_date"] == business_date]
    dates = sorted({c["business_date"] for c in clean} | ({business_date} if business_date else set()))
    with conn:
        with conn.cursor() as cur:
            cur.execute(DDL)
            for d in dates:
                cur.execute("DELETE FROM receipts WHERE business_date=%s", (d,))
            if business_date is None:
                cur.execute("DELETE FROM receipts_quarantine WHERE business_date IS NULL")
            cur.executemany(
                "INSERT INTO receipts VALUES (%(receipt_id)s,%(payer)s,%(merchant)s,%(amount)s,%(currency)s,"
                "%(amount_inr)s,%(ts)s,%(business_date)s,%(is_fraud)s)", clean)
            if business_date is None:
                cur.executemany("INSERT INTO receipts_quarantine(receipt_id, raw, reason) VALUES (%s,%s,%s)",
                                [(rid, str(raw), reason) for rid, raw, reason in quarantine])
    return len(clean), len(quarantine)


def run(path, dsn, business_date=None):
    import psycopg2
    clean, q = transform(extract(path))
    conn = psycopg2.connect(dsn)
    try:
        return load(conn, clean, q, business_date)
    finally:
        conn.close()


if __name__ == "__main__":
    import os, sys
    print(run(sys.argv[1], os.environ.get("PG_DSN", "postgresql://receipts:receipts@localhost:5433/receipts")))
