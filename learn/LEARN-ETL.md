# LEARN: ETL / data pipeline (Python + PostgreSQL)

## What
Extract -> Transform -> Load: read raw receipts, clean and standardise them, write them to a table analysts can trust.

## Why it exists
Upstream feeds redeliver rows, send garbage and get corrected after the fact. Without a pipeline that validates,
dedupes and reloads safely, totals double count or silently lose money.

## How it works
```
receipts.csv --extract--> rows --validate--> clean ----dedupe(receipt_id)----> INR via Decimal --+
                                    \--> (row, reason) --> receipts_quarantine                    |
PostgreSQL: BEGIN; DELETE FROM receipts WHERE business_date = d (each d); INSERT clean; COMMIT <--+
```
- Validation returns `(clean, None)` or `(None, reason)`; the batch never aborts on one bad row.
- Dedupe keeps the first delivery of each `receipt_id`.
- Load is a partition overwrite inside `with conn:` (psycopg2 commits on success, rolls back on exception).

## Where in this repo
- Validation rules: `receipts/etl.py:35-58` (5 reasons, `Decimal` amount, FX table at line 15).
- Dedupe + quarantine split: `receipts/etl.py:61-72`.
- Idempotent load: `receipts/etl.py:75-93` (delete per date lines 83-84, insert lines 87-89).
- Schema: `receipts/etl.py:17-27` (`receipt_id` primary key, index on `business_date`).
- Bad rows injected on purpose: `receipts/generate.py:57-62`.

## How it's verified
`pytest -q tests/test_etl.py` against a real Postgres 16 from Testcontainers: 6 passed on 2026-09-30 (RUN-RESULTS.md).
- `test_bad_rows_quarantined_with_reasons` (line 11): each BAD row gets the right reason.
- `test_duplicates_removed` (22): 3,145 rows - 15 duplicates - 5 bad = 3,125 clean.
- `test_load_into_postgres_and_rerun_is_idempotent` (52): load twice, same count.
- `test_single_partition_reload_touches_only_that_day` (61): other days unchanged.

Limit: when a single partition is reloaded (the Airflow path) quarantine rows are not written (`etl.py:85`, `90`).

## Interview Q&A
- **Q: How do you make a batch load idempotent?** Overwrite a partition (delete + insert in one transaction) keyed on
  the business date, or upsert on a natural key. Partition overwrite also removes rows that vanished from a corrected file.
- **Q: Why not float for money?** Binary floats can't represent 0.10 exactly; sums drift. Use `Decimal` / `NUMERIC`.
- **Q: What do you do with bad rows?** Quarantine with a reason so they can be fixed and replayed; alert if the bad-row
  rate crosses a threshold.
- **Q: Dedupe on what?** The business key (`receipt_id`), not the whole row: a redelivery may differ in metadata.
- **Q: What breaks at 100x volume?** `executemany` row-by-row inserts; use `COPY` or `execute_values`, and load
  partitions in parallel.

## Try it yourself
1. Make the partition reload also write that day's quarantine rows (store `business_date` on the quarantine row when the
   timestamp parses) and add a test.
2. Replace `executemany` with `psycopg2.extras.execute_values` and time a full load before and after.
3. Add a "last write wins" dedupe on a newer `updated_at` instead of "first wins" and test both orders.
