#!/usr/bin/env python3
"""
Regenerates resources/sqlserver_ingestion.generated.yml from the
sqlserver_ingestion_control Delta table (create_control_table.sql).

Bronze is append-only: ingestion just lands whatever the driving-column poll
finds as new rows, no merge/SCD at ingestion time -- that's handled in
src/transform_pipeline/02_silver.py, which reads the same control table
directly. So this script only needs the source/destination mapping and the
driving column, not primary_keys/scd_type.

Meant for the initial bootstrap deploy and for reviewing intended state as a
diff -- runs on demand via the "Generate ingestion resource" GitHub Actions
workflow (.github/workflows/generate-ingestion-resource.yml), which opens a
PR with the result. Once the pipeline exists, resources/daily_pipeline_job.yml
reconciles it against the control table once a day, before that day's
ingestion run (see reconcile_ingestion_pipeline.py) -- this script does not
need to be re-run on every table change.

Usage (CI runs this automatically; for local testing):
    pip install -r scripts/requirements.txt
    databricks auth login   # or set DATABRICKS_HOST / DATABRICKS_TOKEN
    python scripts/generate_ingestion_resource.py --warehouse-id <sql-warehouse-id>
"""

import argparse
from pathlib import Path

from databricks.sdk import WorkspaceClient

from _control_table import fetch_enabled_tables

HEADER = """# GENERATED FILE -- do not hand-edit.
#
# Produced by scripts/generate_ingestion_resource.py from
# `{control_table}`. To add, remove, or disable a table, change a row in
# that table -- resources/daily_pipeline_job.yml reconciles the deployed
# pipeline against it once a day, before that day's ingestion run; re-run
# this script only if you want to review the change as a git diff or redo
# the initial bootstrap deploy.
#
# Bronze is append-only -- table_configuration only sets the driving column
# used for incremental extraction, no primary_keys/scd_type (that merge/SCD
# logic lives in src/transform_pipeline/02_silver.py instead).
#
# UNVERIFIED: confirm `table_configuration.driving_column` is the right key
# for query-based ingestion in your workspace (`databricks bundle schema` or
# the Lakeflow Connect SQL Server docs) before deploying. Also confirm
# whether query-based ingestion still needs a separate gateway pipeline --
# CDC-based ingestion does, this assumes query-based does not.

resources:
  pipelines:
    sqlserver_ingestion:
      name: sqlserver-ingestion-pipeline-${{bundle.target}}
      catalog: ${{var.bronze_catalog}}
      schema: ${{var.bronze_schema}}
      ingestion_definition:
        connection_name: <sqlserver_connection_name>
        objects:
"""

OBJECT_TEMPLATE = """          - table:
              source_catalog: {source_database}
              source_schema: {source_schema}
              source_table: {source_table}
              destination_catalog: {destination_catalog}
              destination_schema: {destination_schema}
              destination_table: {destination_table}
              table_configuration:
                driving_column: {driving_column}
"""


def render(control_table: str, rows: list[dict]) -> str:
    if not rows:
        raise SystemExit(f"No enabled rows in {control_table} -- refusing to generate an empty ingestion pipeline.")

    objects = "".join(OBJECT_TEMPLATE.format(**row) for row in rows)
    return HEADER.format(control_table=control_table) + objects


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--warehouse-id", required=True, help="SQL warehouse ID to run the control-table query against")
    parser.add_argument("--control-table", default="main.sqlserver_ingestion.sqlserver_ingestion_control")
    parser.add_argument(
        "--output",
        default=str(Path(__file__).resolve().parent.parent / "resources" / "sqlserver_ingestion.generated.yml"),
    )
    args = parser.parse_args()

    client = WorkspaceClient()
    rows = fetch_enabled_tables(client, args.warehouse_id, args.control_table)
    yaml_text = render(args.control_table, rows)

    Path(args.output).write_text(yaml_text)
    print(f"Wrote {len(rows)} table(s) to {args.output}")


if __name__ == "__main__":
    main()
