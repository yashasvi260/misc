-- Run once to create the ingestion control table. This table is the source
-- of truth for which SQL Server tables Lakeflow Connect ingests --
-- resources/sqlserver_ingestion.generated.yml is generated from it by
-- scripts/generate_ingestion_resource.py. Never hand-edit that yml file;
-- add/change/disable a row here and re-run the generator instead.

CREATE TABLE IF NOT EXISTS main.sqlserver_ingestion.sqlserver_ingestion_control (
  source_database     STRING  NOT NULL COMMENT 'SQL Server database name',
  source_schema       STRING  NOT NULL,
  source_table        STRING  NOT NULL,
  destination_catalog STRING  NOT NULL,
  destination_schema  STRING  NOT NULL,
  destination_table   STRING  NOT NULL,
  driving_column       STRING  NOT NULL COMMENT 'Monotonically increasing/changing column (e.g. a rowversion or LastModifiedDate column) used to detect new or changed rows -- there is no CDC to rely on for query-based ingestion.',
  primary_keys          ARRAY<STRING> NOT NULL COMMENT 'Source primary key column(s), used to merge/upsert into the destination table.',
  scd_type               INT     NOT NULL COMMENT '1 = destination holds current state only, 2 = destination keeps full history.',
  enabled                 BOOLEAN NOT NULL COMMENT 'Set to false to stop ingesting a table -- the generator skips disabled rows -- without deleting its config.',
  updated_by               STRING,
  updated_at                TIMESTAMP
)
USING DELTA
COMMENT 'Source of truth for Lakeflow Connect SQL Server ingestion. resources/sqlserver_ingestion.generated.yml is generated from this table.';

-- Example seed rows matching the placeholder tables referenced in
-- src/transform_pipeline/. Replace with your real source tables before
-- running the generator for the first time.
INSERT INTO main.sqlserver_ingestion.sqlserver_ingestion_control VALUES
  ('<source_database>', 'dbo', 'Customers', 'main', 'sqlserver_bronze', 'customers',
   'ModifiedDate', array('CustomerId'), 2, true, current_user(), current_timestamp()),
  ('<source_database>', 'dbo', 'Orders', 'main', 'sqlserver_bronze', 'orders',
   'ModifiedDate', array('OrderId'), 1, true, current_user(), current_timestamp());

-- To add a table: INSERT a new row.
-- To disable a table without losing its config:
--   UPDATE main.sqlserver_ingestion.sqlserver_ingestion_control
--   SET enabled = false, updated_by = current_user(), updated_at = current_timestamp()
--   WHERE source_table = 'Orders';
-- Then re-run scripts/generate_ingestion_resource.py and `databricks bundle deploy`.
