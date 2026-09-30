"""PySpark (local mode) aggregations over cleaned receipts.

daily_totals: sum/count per business date x currency x payer.
rolling_7d:   per payer, rolling 7-day INR spend using a range window over
              day numbers (so missing days are handled correctly, unlike a
              rows-based window).
"""
from pyspark.sql import SparkSession, Window, functions as F

SECONDS_PER_DAY = 86400


def spark_session(app="receipts-spend"):
    return (SparkSession.builder.master("local[2]").appName(app)
            .config("spark.sql.shuffle.partitions", "4").config("spark.ui.enabled", "false")
            .getOrCreate())


def daily_totals(df):
    return (df.withColumn("business_date", F.to_date("ts"))
              .groupBy("business_date", "currency", "payer")
              .agg(F.round(F.sum("amount"), 2).alias("total"), F.count("*").alias("n")))


def rolling_7d(df):
    daily = (df.withColumn("business_date", F.to_date("ts"))
               .groupBy("payer", "business_date").agg(F.sum("amount_inr").alias("day_inr")))
    w = (Window.partitionBy("payer").orderBy(F.col("business_date").cast("timestamp").cast("long"))
               .rangeBetween(-6 * SECONDS_PER_DAY, 0))
    return daily.withColumn("rolling_7d_inr", F.round(F.sum("day_inr").over(w), 2))


if __name__ == "__main__":
    import sys
    s = spark_session()
    df = (s.read.option("header", True).option("inferSchema", True).csv(sys.argv[1])
            .where("amount > 0 AND currency IN ('INR','USD','EUR','GBP')").dropDuplicates(["receipt_id"]))
    rates = {"INR": 1.0, "USD": 83.2, "EUR": 90.1, "GBP": 105.4}
    expr = F.create_map(*[x for k, v in rates.items() for x in (F.lit(k), F.lit(v))])
    df = df.withColumn("amount_inr", F.col("amount") * expr[F.col("currency")])
    daily_totals(df).orderBy("business_date").show(10)
    rolling_7d(df).orderBy(F.desc("rolling_7d_inr")).show(10)
