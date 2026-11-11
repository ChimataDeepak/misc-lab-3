# LEARN: Apache Spark (PySpark, local mode)

## What
A distributed engine for DataFrame/SQL transformations. Code describes a plan; Spark splits it into stages and tasks
over partitions. Here it runs `local[2]` (2 threads on one machine), not a cluster.

## Why it exists
When data no longer fits one machine (or one process), you need group-bys and windows that run in parallel and spill to
disk. The same code runs on a laptop and on a cluster.

## How it works
```
CSV -> filter + dropDuplicates -> withColumn(amount_inr)
   -> daily_totals: groupBy(business_date, currency, payer).agg(sum, count)      [shuffle by key]
   -> rolling_7d:   groupBy(payer, date).sum -> Window.partitionBy(payer)
                    .orderBy(epoch seconds).rangeBetween(-6 days, 0)            [range, not rows]
```
`rangeBetween` frames by **value** (dates within 6 days); `rowsBetween(-6, 0)` frames by **count** (last 7 rows),
which is wrong when a payer has no receipts on some days.

## Where in this repo
- Session: `spark/daily_spend.py:13-16` (`local[2]`, 4 shuffle partitions, UI off).
- Daily totals: `spark/daily_spend.py:19-22`.
- Range window: `spark/daily_spend.py:25-30`.
- CLI entry with FX map: `spark/daily_spend.py:33-42`.

## How it's verified
`pytest -q tests/test_spark.py`: 2 passed on 2026-09-30 (PySpark 4.2.0, Java 21; RUN-RESULTS.md).
`test_rolling_7_day_window_is_range_based` (`tests/test_spark.py:33`) has a deliberate gap: 2026-09-09 must include
09-05 but not 09-01; a rows-based window would fail it.

## Interview Q&A
- **Q: Transformation vs action?** Transformations (`groupBy`, `withColumn`) build the plan lazily; actions (`collect`,
  `show`, `write`) execute it.
- **Q: What is a shuffle and why is it expensive?** Repartitioning rows by key across executors (disk + network). Here
  `spark.sql.shuffle.partitions=4` because the default 200 is far too many for tiny data.
- **Q: Data skew?** One payer with most rows makes one task slow; salt the key or use AQE skew-join handling.
- **Q: When not to use Spark?** 3k rows: pandas or SQL is faster. Spark pays off when data or compute outgrows one node.

## Try it yourself
1. Change the window to `rowsBetween(-6, 0)`, run the test, and explain the failure.
2. Write `daily_totals` to Parquet partitioned by `business_date` and read back only one date (partition pruning).
3. Call `.explain()` on `rolling_7d` and find the `Exchange` (shuffle) nodes.
