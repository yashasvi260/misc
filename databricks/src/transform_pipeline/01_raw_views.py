# Raw layer.
#
# Bronze is append-only: the ingestion pipeline lands every row a poll finds
# as a new insert into ${bronze_catalog}.${bronze_schema}.<table> -- it never
# updates or merges existing rows (see resources/sqlserver_ingestion.generated.yml
# and scripts/create_control_table.sql). That makes a streaming read safe
# here; dedup and current-state/history logic happen in 02_silver.py.
#
# One view per enabled row in the control table, generated in a loop so
# adding a table there is enough -- no edit needed here.

from pyspark import pipelines as dp

CONTROL_TABLE = spark.conf.get("control_table")
BRONZE_CATALOG = spark.conf.get("bronze_catalog")
BRONZE_SCHEMA = spark.conf.get("bronze_schema")

enabled_tables = (
    spark.table(CONTROL_TABLE)
    .where("enabled")
    .select("destination_table")
    .distinct()
    .collect()
)

for row in enabled_tables:
    dest_table = row["destination_table"]

    def _make_raw_view(dest_table=dest_table):
        @dp.view(name=f"raw_{dest_table}")
        def _raw_view():
            return spark.readStream.table(f"{BRONZE_CATALOG}.{BRONZE_SCHEMA}.{dest_table}")

        return _raw_view

    _make_raw_view()
