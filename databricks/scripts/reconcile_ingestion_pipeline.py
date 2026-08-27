#!/usr/bin/env python3
"""
Reconciles the live SQL Server ingestion pipeline's object list against the
sqlserver_ingestion_control Delta table. Runs once a day as the first task
in resources/daily_pipeline_job.yml, immediately before that job's ingestion
and transform pipeline tasks, so a control-table change (add/disable a
table) is picked up right before it matters -- without anyone running
`databricks bundle deploy` by hand, and without polling the table hourly.

This does a GET -> modify objects -> PUT against the Pipelines API, since
the update endpoint is a full-spec replace, not a merge patch -- sending a
partial body would risk wiping out the pipeline's other settings
(catalog/schema/name/etc).

UNVERIFIED, confirm before enabling the schedule:
  - That `GET /api/2.0/pipelines/{id}` nests the pipeline definition under a
    top-level `spec` key (assumed below) -- run once with --dry-run and read
    the printed response if this script errors on that assumption.
  - The `table_configuration` body shape (see generate_ingestion_resource.py
    for the same caveat).

Usage:
    pip install -r scripts/requirements.txt
    databricks auth login   # or rely on the job's own identity when run as a Databricks Job
    python scripts/reconcile_ingestion_pipeline.py --warehouse-id <id> --pipeline-name <name>       # dry run, prints only
    python scripts/reconcile_ingestion_pipeline.py --warehouse-id <id> --pipeline-name <name> --apply  # actually updates
"""

import argparse
import json

from databricks.sdk import WorkspaceClient

from _control_table import fetch_enabled_tables


def find_pipeline_id(client: WorkspaceClient, pipeline_name: str) -> str:
    for p in client.pipelines.list_pipelines():
        if p.name == pipeline_name:
            return p.pipeline_id
    raise SystemExit(f"No pipeline named {pipeline_name!r} found -- deploy the bundle once to create it first.")


def build_objects(rows: list[dict]) -> list[dict]:
    return [
        {
            "table": {
                "source_catalog": row["source_database"],
                "source_schema": row["source_schema"],
                "source_table": row["source_table"],
                "destination_catalog": row["destination_catalog"],
                "destination_schema": row["destination_schema"],
                "destination_table": row["destination_table"],
                "table_configuration": {"driving_column": row["driving_column"]},
            }
        }
        for row in rows
    ]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--warehouse-id", required=True)
    parser.add_argument("--pipeline-name", required=True)
    parser.add_argument("--control-table", default="main.sqlserver_ingestion.sqlserver_ingestion_control")
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Actually PUT the reconciled spec. Without this flag, prints what would change and exits.",
    )
    args = parser.parse_args()

    client = WorkspaceClient()
    rows = fetch_enabled_tables(client, args.warehouse_id, args.control_table)
    if not rows:
        raise SystemExit(f"No enabled rows in {args.control_table} -- refusing to push an empty object list.")

    pipeline_id = find_pipeline_id(client, args.pipeline_name)
    objects = build_objects(rows)

    current = client.api_client.do("GET", f"/api/2.0/pipelines/{pipeline_id}")
    spec = current.get("spec", current)

    if not args.apply:
        print(f"[dry run] pipeline {args.pipeline_name} ({pipeline_id}) -- would set {len(objects)} object(s):")
        print(json.dumps(objects, indent=2))
        print("\nFull current spec, for verifying the `spec` key assumption above:")
        print(json.dumps(current, indent=2))
        print("\nRe-run with --apply once this looks right.")
        return

    spec.setdefault("ingestion_definition", {})["objects"] = objects
    client.api_client.do("PUT", f"/api/2.0/pipelines/{pipeline_id}", body=spec)
    print(f"Reconciled {len(objects)} table(s) into pipeline {args.pipeline_name} ({pipeline_id})")


if __name__ == "__main__":
    main()
