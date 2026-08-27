"""Shared helper for generate_ingestion_resource.py and
reconcile_ingestion_pipeline.py: read the enabled rows of the ingestion
control table (see create_control_table.sql) via a SQL warehouse.
"""

from databricks.sdk import WorkspaceClient


def fetch_enabled_tables(client: WorkspaceClient, warehouse_id: str, control_table: str):
    statement = f"""
        SELECT source_database, source_schema, source_table,
               destination_catalog, destination_schema, destination_table,
               driving_column, primary_keys, scd_type
        FROM {control_table}
        WHERE enabled = true
        ORDER BY source_schema, source_table
    """
    result = client.statement_execution.execute_statement(
        warehouse_id=warehouse_id, statement=statement, wait_timeout="30s"
    )
    if result.status.state.value != "SUCCEEDED":
        raise RuntimeError(f"Control table query failed: {result.status}")

    columns = [c.name for c in result.manifest.schema.columns]
    rows = result.result.data_array or []
    return [dict(zip(columns, row)) for row in rows]
