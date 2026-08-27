# Gold layer: business-facing aggregates built on top of the silver tables.
#
# Column names match the SQL Server source casing (CustomerId, OrderId, ...)
# -- 02_silver.py's create_auto_cdc_flow doesn't rename columns, it just
# dedups/historizes whatever raw_<table> has. silver_customers is scd_type=2
# so it carries __START_AT/__END_AT and needs the __END_AT IS NULL filter to
# get the current record per customer; silver_orders is scd_type=1 (current
# state only), so no such filter applies there.

from pyspark.sql.functions import col, count, current_date, date_sub
from pyspark.sql.functions import sum as _sum

from pyspark import pipelines as dp


@dp.materialized_view(
    name="gold_customer_order_summary",
    comment="Per-customer order totals, joined to the current customer record.",
)
def gold_customer_order_summary():
    orders = dp.read("silver_orders")
    customers = dp.read("silver_customers").where(col("__END_AT").isNull())

    return (
        orders.groupBy("CustomerId")
        .agg(
            count("OrderId").alias("order_count"),
            _sum("TotalAmount").alias("lifetime_value"),
        )
        .join(customers, customers.CustomerId == orders.CustomerId, "left")
        .select(
            orders["CustomerId"],
            customers["CustomerName"],
            "order_count",
            "lifetime_value",
        )
    )


@dp.materialized_view(
    name="gold_daily_order_volume",
    comment="Order counts and revenue by day, trailing 90 days.",
)
def gold_daily_order_volume():
    return (
        dp.read("silver_orders")
        .where(col("OrderDate") >= date_sub(current_date(), 90))
        .groupBy("OrderDate")
        .agg(count("OrderId").alias("order_count"), _sum("TotalAmount").alias("revenue"))
    )
