# LEARN: Hadoop MapReduce (Streaming)

## What
MapReduce: a mapper turns each input record into key/value pairs, the framework sorts and groups by key, a reducer
aggregates each key. Hadoop Streaming lets any executable reading stdin and writing stdout be the mapper or reducer.

## Why it exists
It was the first widely used way to process files bigger than one disk over a cluster (HDFS + YARN). Spark replaced it
for most work, but the map / shuffle-sort / reduce model is still how distributed aggregation works.

## How it works
```
receipts.csv --mapper.awk--> "EUR\t12.50" ...  --(framework sort by key)-->  EUR 12.50
                bad row -> stderr "reporter:counter:receipts,bad_rows,1"       EUR 30.00 --reducer.awk--> EUR\t855\t<total>
```
The reducer relies on sorted input: it emits a line each time the key changes.

## Where in this repo
- Mapper: `hadoop/mapper.awk:5-12` (drops header and rows without 7 fields, counts invalid amount/currency).
- Reducer: `hadoop/reducer.awk:1-5`.
- Job: `hadoop/run-streaming.sh:9-14` (`mapreduce.framework.name=local`, `fs.defaultFS=file:///`, `apache/hadoop:3.4.1`).

## How it's verified
- `pytest -q tests/test_hadoop.py`: reproduces map -> `sort` -> reduce locally; 1 passed on 2026-09-30.
- `./hadoop/run-streaming.sh data/receipts.csv` on 2026-09-30: EUR 855 / GBP 481 / INR 1046 / USD 760 = 3,142 lines,
  `bad_rows=3` (RUN-RESULTS.md).

Honest limits: local job runner in one container, no HDFS or YARN cluster; the amd64 image ran under emulation on arm64.
The mapper does not dedupe and does not check timestamp or payer, so 3,142 includes the 15 duplicate deliveries and the
bad-timestamp and empty-payer rows; it is not comparable with the ETL's 3,125 clean rows.

## Interview Q&A
- **Q: What does the combiner do?** A mini-reducer on the map side to shrink shuffle data; valid here because sum and
  count are associative.
- **Q: Why does the reducer need sorted input?** Grouping is done by the framework's sort; the reducer just watches for
  the key to change.
- **Q: How do counters help?** Cheap, job-wide metrics (bad rows) without writing a side output.
- **Q: MapReduce vs Spark?** MapReduce writes to disk between every stage; Spark keeps intermediate data in memory and
  plans multi-stage DAGs.

## Try it yourself
1. Add a combiner (`-combiner "awk -f reducer.awk"`; note the reducer must then also accept `count total` input) and
   compare "Map output records" vs "Reduce input records".
2. Explain why a mapper alone can't dedupe across input splits, then add a first job keyed on `receipt_id` that keeps
   one row per id and feed its output to the currency job.
3. Count the bad-timestamp row too and make `bad_rows` match the ETL's 5.
