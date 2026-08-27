# Silver layer.
#
# Bronze/raw is append-only (see 01_raw_views.py), so dedup and history live
# here: one auto CDC flow per enabled control-table row, keyed by that row's
# primary_keys and sequenced by driving_column. scd_type=1 keeps only
# current state; scd_type=2 keeps full history via __START_AT/__END_AT.
#
# Generated in a loop, same as 01_raw_views.py -- adding a table to the
# control table is enough, no edit needed here.

from pyspark import pipelines as dp

CONTROL_TABLE = spark.conf.get("control_table")

enabled_tables = spark.table(CONTROL_TABLE).where("enabled").collect()

for row in enabled_tables:
    dest_table = row["destination_table"]
    primary_keys = row["primary_keys"]
    driving_column = row["driving_column"]
    scd_type = row["scd_type"]

    def _make_silver_flow(
        dest_table=dest_table,
        primary_keys=primary_keys,
        driving_column=driving_column,
        scd_type=scd_type,
    ):
        silver_table = f"silver_{dest_table}"
        dp.create_streaming_table(name=silver_table)
        dp.create_auto_cdc_flow(
            target=silver_table,
            source=f"raw_{dest_table}",
            keys=primary_keys,
            sequence_by=driving_column,
            stored_as_scd_type=scd_type,
        )

    _make_silver_flow()
