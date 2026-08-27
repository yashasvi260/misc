# SQL Server → Lakeflow → Spark Declarative Pipeline

Databricks Asset Bundle with three pieces:

1. **`sqlserver_ingestion`** (`resources/sqlserver_ingestion.generated.yml`) — a Lakeflow Connect **query-based** ingestion pipeline for SQL Server. CDC isn't enabled on the source, so each table is pulled incrementally using a driving/watermark column, and landed **append-only** into bronze — every poll writes new rows, nothing is merged or updated in place.
2. **`transform_pipeline`** (`resources/transform_pipeline.yml`, code in `src/transform_pipeline/`) — a Spark Declarative Pipeline that turns append-only bronze into deduped/historized silver tables and aggregated gold tables.
3. **`daily_sqlserver_pipeline`** (`resources/daily_pipeline_job.yml`) — a single Databricks Job, scheduled once a day, that runs the other two in order: reconcile the control table → run ingestion → run transform.

The first two are Lakeflow/Declarative Pipeline resources with no schedule of their own — the daily job is what actually triggers them, in order, once a day.

## Why bronze is append-only

Other ingestion in this workspace already lands as append-only, and it sidesteps two real risks of merging at ingestion time:

- **Streaming reads break on in-place updates.** `spark.readStream` on a Delta table only supports appends; a table receiving merges/upserts errors with "streaming source only supports appends" unless you also wire up Change Data Feed. Append-only bronze keeps `01_raw_views.py`'s streaming reads simple and correct — including when the pipeline is triggered once a day rather than continuously, since Structured Streaming's checkpointing just picks up wherever the previous run left off.
- **Merge/SCD logic at ingestion time depends on unverified Lakeflow Connect behavior** (see the flagged items below). `dp.create_auto_cdc_flow` is a stable, well-documented Spark Declarative Pipelines API — pushing dedup/SCD into silver, where this scaffold has high confidence in the API, is lower-risk than relying on ingestion-time merge semantics that couldn't be confirmed.

The tradeoff: bronze accumulates every polled row forever (no compaction/TTL is set up here), and "current state" only exists from silver onward.

## The table list is data, not code

Every table Lakeflow Connect ingests, and how silver processes it, is a row in a Delta control table — not something hand-edited in bundle YAML or pipeline code. Adding, removing, or disabling a table is an `INSERT`/`UPDATE` against that table.

**Control table**: `main.sqlserver_ingestion.sqlserver_ingestion_control` (DDL + example rows in `scripts/create_control_table.sql`). One row per source table:

| column | purpose |
|---|---|
| `source_database` / `source_schema` / `source_table` | where the table lives in SQL Server |
| `destination_catalog` / `destination_schema` / `destination_table` | where Lakeflow Connect lands it in Unity Catalog (bronze) |
| `driving_column` | watermark column used to find new/changed rows since the last pull (no CDC to rely on) |
| `primary_keys` | key column(s) `02_silver.py` merges/dedups on |
| `scd_type` | `1` = silver holds current state only, `2` = silver keeps full history (`__START_AT`/`__END_AT`) |
| `enabled` | `false` disables a table without deleting its config — skipped by the generator, the reconciler, and both `01_raw_views.py`/`02_silver.py` |

This control table drives three consumers:

```
resources/sqlserver_ingestion.generated.yml   which tables the ingestion pipeline pulls from SQL Server (bronze-in)
src/transform_pipeline/01_raw_views.py        one streaming raw_<table> view per enabled row     (bronze-out)
src/transform_pipeline/02_silver.py           one create_auto_cdc_flow per enabled row            (silver)
```

**Workflow to add/change/disable a table:**

```sql
-- add a table
INSERT INTO main.sqlserver_ingestion.sqlserver_ingestion_control VALUES
  ('SalesDB', 'dbo', 'Products', 'main', 'sqlserver_bronze', 'products',
   'ModifiedDate', array('ProductId'), 1, true, current_user(), current_timestamp());

-- disable a table
UPDATE main.sqlserver_ingestion.sqlserver_ingestion_control
SET enabled = false, updated_by = current_user(), updated_at = current_timestamp()
WHERE source_table = 'Orders';
```

`01_raw_views.py`/`02_silver.py` pick up the change the next time `transform_pipeline` runs — no redeploy needed. The ingestion pipeline's table list needs its bundle resource regenerated, which happens one of two ways:

- **Automatically** — the `reconcile` task in `daily_sqlserver_pipeline` (see below) checks the control table once a day, right before that day's ingestion run.
- **On demand, via GitHub Actions** — for the initial bootstrap deploy, or any time you want to review a change as a pull request before it's live:

  1. Run the **Generate ingestion resource** workflow (`.github/workflows/generate-ingestion-resource.yml`, manual `workflow_dispatch` trigger) — it regenerates `sqlserver_ingestion.generated.yml` from the control table and opens a PR with the diff.
  2. Review and merge the PR.
  3. Merging to `main` triggers **Deploy Databricks bundle** (`.github/workflows/deploy-databricks-bundle.yml`), which runs `databricks bundle deploy`.

  Both workflows need `DATABRICKS_HOST` / `DATABRICKS_TOKEN` configured as repo secrets, and the generator workflow needs a `SQL_WAREHOUSE_ID` repo variable. Running the generator locally still works too, for testing:

  ```bash
  pip install -r scripts/requirements.txt
  databricks auth login   # or set DATABRICKS_HOST / DATABRICKS_TOKEN
  python scripts/generate_ingestion_resource.py --warehouse-id <sql-warehouse-id>
  ```

## The daily job: `daily_sqlserver_pipeline`

One scheduled job (`resources/daily_pipeline_job.yml`), three tasks, each depending on the last:

```
reconcile  →  run_ingestion  →  run_transform
```

- **`reconcile`** runs `scripts/reconcile_ingestion_pipeline.py`, which reads the control table and updates the **already-deployed** ingestion pipeline's `ingestion_definition.objects` directly via the Pipelines REST API (`GET` the current spec, replace only `objects`, `PUT` the full spec back) — it doesn't touch the bundle or require the CLI. It's a full GET-modify-PUT, not a partial patch, specifically so a bad assumption about the API can't silently wipe out the pipeline's other settings (catalog, schema, name) — worst case it's a no-op.
- **`run_ingestion`** and **`run_transform`** are `pipeline_task`s that trigger `sqlserver_ingestion` and `transform_pipeline` directly — this is also what gives those two resources their daily schedule, since neither has one of its own.
- **`depends_on` makes the chain fail-closed.** If `reconcile` errors (e.g. the control table is unreachable), `run_ingestion` and `run_transform` never run that day, instead of running against a stale or partially-reconciled object list. And `run_transform` only starts once `run_ingestion` has finished landing that day's rows into bronze — `transform_pipeline` reads whatever is in bronze at the time it runs, so this ordering matters.

Reconciling once a day, right before ingestion, is also why there's no separate hourly polling job: a control-table change made any time before that day's run is picked up in the same run that needs it, with no wasted checks in between.

**It ships paused, and the `reconcile` task runs without `--apply` by default.** Before turning it on:

```bash
python scripts/reconcile_ingestion_pipeline.py \
  --warehouse-id <sql-warehouse-id> \
  --pipeline-name sqlserver-ingestion-pipeline-dev
```

Run that by hand first and read the dry-run output — it prints the full current pipeline spec so you can confirm the `spec` key nesting (see unverified list below) matches what your workspace actually returns. Only once that's confirmed: add `--apply` to the `reconcile` task's parameters in `resources/daily_pipeline_job.yml` and flip `pause_status` to `UNPAUSED`.

## Layout

```
databricks.yml                                      bundle root: variables + targets
resources/
  sqlserver_ingestion.generated.yml                  generated — do not hand-edit
  transform_pipeline.yml                             declarative pipeline definition
  daily_pipeline_job.yml                             daily job: reconcile -> ingest -> transform
scripts/
  create_control_table.sql                           control table DDL + example rows
  generate_ingestion_resource.py                      control table -> generated yml
  reconcile_ingestion_pipeline.py                      control table -> deployed pipeline (REST API)
  _control_table.py                                    shared control-table read helper
src/transform_pipeline/
  01_raw_views.py                                     one streaming raw_<table> view per enabled row
  02_silver.py                                         one create_auto_cdc_flow per enabled row
  03_gold.py                                           per-customer and daily aggregates
.github/workflows/
  generate-ingestion-resource.yml                     on demand: control table -> generated yml -> PR
  deploy-databricks-bundle.yml                         on merge to main: databricks bundle deploy
```

## Before deploying — things flagged as unverified

This scaffold's structure is solid, but a few specifics couldn't be confirmed against a real workspace and are called out in comments where they're used:

- **`table_configuration.driving_column`** (`resources/sqlserver_ingestion.generated.yml`, `scripts/generate_ingestion_resource.py`, `scripts/reconcile_ingestion_pipeline.py`) — best-guess field name for query-based ingestion's watermark column. Confirm the real schema with `databricks bundle schema` or the Lakeflow Connect SQL Server docs in your workspace before deploying.
- **No gateway pipeline** — CDC-based SQL Server ingestion requires a separate gateway pipeline; this assumes query-based mode doesn't. Verify that in your workspace before deploying; if it does, add a `gateway_definition` pipeline resource back and reference it from `ingestion_definition.ingestion_gateway_id` instead of `connection_name`.
- **Pipelines API `spec` nesting** (`scripts/reconcile_ingestion_pipeline.py`) — assumes `GET /api/2.0/pipelines/{id}` returns the editable fields under a top-level `spec` key (falling back to the top-level response if not). Confirmed by reading the dry-run output before ever passing `--apply` — see above.
- **Deploy target** (`.github/workflows/deploy-databricks-bundle.yml`) — deploys to `-t prod` on every merge to `main`; confirm that's the target you want CI deploying to (see `databricks.yml` for what's configured).

`__START_AT`/`__END_AT` for `scd_type: 2` history is *not* on this list — those are produced by `dp.create_auto_cdc_flow` itself in `02_silver.py`, a stable, documented part of the Spark Declarative Pipelines API, not something this scaffold is guessing at. The `pipeline_task`/`depends_on` job structure in `daily_pipeline_job.yml` and the `${resources.pipelines.<key>.id}` cross-reference are also standard, documented Jobs/DAB features, not guesses.

Also still required before first deploy:

- **`databricks.yml`**: `<your-workspace-url>` for each target, `<sql-warehouse-id>` for `control_table_warehouse_id`, and the other `variables` defaults (catalog/schema names) if you're not using `main`.
- **`resources/sqlserver_ingestion.generated.yml`** / **`scripts/create_control_table.sql`**: a Unity Catalog `CONNECTION` to the SQL Server instance (`<sqlserver_connection_name>`), and `<source_database>` — the control table rows are placeholders (`Customers`/`Orders`), swap for your real source schema and re-run the generator.
- **`resources/daily_pipeline_job.yml`**: `<node-type-id>` for the `reconcile` task's cluster, and the `quartz_cron_expression` / `timezone_id` if 06:00 UTC isn't the time you want this to run.
- **GitHub Actions**: repo secrets `DATABRICKS_HOST` and `DATABRICKS_TOKEN` (both workflows), and repo variable `SQL_WAREHOUSE_ID` (generator workflow only) — under Settings → Secrets and variables → Actions.

## Deploy

```bash
databricks bundle validate -t dev
databricks bundle deploy -t dev

databricks bundle run sqlserver_ingestion -t dev   # ad hoc / first run, after the control table has real rows
databricks bundle run transform_pipeline -t dev    # ad hoc / first run
```

Day to day, neither of those manual runs is needed — `daily_sqlserver_pipeline` triggers both automatically once it's unpaused.
