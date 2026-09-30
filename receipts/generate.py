"""Deterministic synthetic receipt/payment generator (seeded).

Produces realistic-looking receipts plus injected fraud patterns and a few
deliberately bad rows (so the ETL quarantine path has something to catch).
Fraud patterns:
  - burst: many small payments from one payer within minutes (card testing)
  - large_foreign: unusually large amount in a currency the payer never uses
  - night_high: high-value payment between 01:00 and 04:00 to a new merchant
"""
import csv
import random
from datetime import datetime, timedelta

PAYERS = [f"payer_{i:03d}" for i in range(60)]
MERCHANTS = ["grocer", "fuel", "cafe", "airline", "hotel", "pharmacy", "electronics", "books"]
CURRENCIES = ["INR", "USD", "EUR", "GBP"]
FIELDS = ["receipt_id", "payer", "merchant", "amount", "currency", "ts", "is_fraud"]
START = datetime(2026, 9, 1)


def generate(n=3000, seed=42, days=28):
    rng = random.Random(seed)
    home = {p: rng.choice(CURRENCIES) for p in PAYERS}
    rows = []
    rid = 0

    def add(payer, merchant, amount, cur, ts, fraud):
        nonlocal rid
        rid += 1
        rows.append({"receipt_id": f"R{rid:06d}", "payer": payer, "merchant": merchant,
                     "amount": f"{amount:.2f}", "currency": cur,
                     "ts": ts.isoformat(timespec="seconds"), "is_fraud": int(fraud)})

    for _ in range(n):
        p = rng.choice(PAYERS)
        ts = START + timedelta(days=rng.randrange(days), hours=rng.randint(7, 22), minutes=rng.randrange(60))
        add(p, rng.choice(MERCHANTS), round(rng.lognormvariate(3.2, 0.8), 2), home[p], ts, False)
    # fraud: bursts
    for _ in range(12):
        p = rng.choice(PAYERS)
        t0 = START + timedelta(days=rng.randrange(days), hours=rng.randint(0, 23))
        for k in range(rng.randint(5, 9)):
            add(p, "electronics", round(rng.uniform(1, 5), 2), home[p], t0 + timedelta(minutes=k), True)
    # fraud: large foreign
    for _ in range(25):
        p = rng.choice(PAYERS)
        cur = rng.choice([c for c in CURRENCIES if c != home[p]])
        ts = START + timedelta(days=rng.randrange(days), hours=rng.randint(0, 23))
        add(p, rng.choice(["airline", "hotel", "electronics"]), round(rng.uniform(900, 4000), 2), cur, ts, True)
    # fraud: night high value
    for _ in range(25):
        p = rng.choice(PAYERS)
        ts = START + timedelta(days=rng.randrange(days), hours=rng.randint(1, 3), minutes=rng.randrange(60))
        add(p, "electronics", round(rng.uniform(600, 2500), 2), home[p], ts, True)
    rng.shuffle(rows)
    # duplicates (same receipt delivered twice) and bad rows
    rows += [dict(r) for r in rng.sample(rows, 15)]
    rows.append({**rows[0], "receipt_id": "BAD1", "amount": "-5.00"})
    rows.append({**rows[1], "receipt_id": "BAD2", "currency": "XYZ"})
    rows.append({**rows[2], "receipt_id": "BAD3", "amount": "abc"})
    rows.append({**rows[3], "receipt_id": "BAD4", "ts": "not-a-date"})
    rows.append({**rows[4], "receipt_id": "BAD5", "payer": ""})
    return rows


def write_csv(path, rows):
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(rows)


if __name__ == "__main__":
    import sys
    out = sys.argv[1] if len(sys.argv) > 1 else "data/receipts.csv"
    import os
    os.makedirs(os.path.dirname(out) or ".", exist_ok=True)
    rows = generate()
    write_csv(out, rows)
    print(f"wrote {len(rows)} rows to {out}")
