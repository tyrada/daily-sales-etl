# Daily Sales ETL

A small portfolio project that turns one daily sales CSV into clean, auditable PostgreSQL records. It demonstrates deterministic data generation, schema and row validation, quarantine handling, idempotent loading, transaction boundaries, and operational audit records without an orchestration framework.

## Problem and design

Daily source files can contain bad types, missing values, and repeated transactions. The pipeline must keep invalid data inspectable, load good data exactly once, and leave enough metadata to troubleshoot every attempt.

```text
deterministic generator -> daily CSV -> validate/clean -> valid rows -> PostgreSQL sales
                                             |                         PostgreSQL etl_runs
                                             +-> rejected CSV
```

The CLI reads every source field as text, checks required columns, normalizes types, and rounds prices to two decimal places with `Decimal`. Later occurrences of a transaction ID in the same file are quarantined. The `sales.transaction_id` primary key plus `ON CONFLICT DO NOTHING` makes database loads idempotent across runs.

Audit inserts and updates use their own short transactions. The sales batch uses one separate transaction, so any failed insert rolls back the whole batch while the run can still be marked `FAILED`. All SQL values are passed as parameters.

## Schema

`sales` stores the stable `transaction_id`, sale date, customer and product IDs, positive quantity, positive `NUMERIC(12,2)` price, three-letter currency, source filename, and load timestamp.

`etl_runs` stores a UUID run ID, source filename, `RUNNING`/`SUCCEEDED`/`FAILED` status, start and finish timestamps, duration, input/loaded/rejected counts, and a bounded error message. See [`sql/init.sql`](sql/init.sql) for constraints and indexes.

Required CSV columns:

```text
transaction_id,transaction_date,customer_id,product_id,quantity,unit_price,currency
```

## Local setup and commands

Prerequisites: Python 3.11+ and Docker Compose. The examples use a POSIX shell; on PowerShell, use `Copy-Item`, `.\.venv\Scripts\Activate.ps1`, and `$env:DATABASE_URL=...`.

```bash
cp .env.example .env
# Replace the local password in .env, including the DATABASE_URL value.

python -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[dev]'

docker compose up -d
export DATABASE_URL='postgresql://sales_app:replace-with-a-local-password@localhost:5432/sales'
daily-sales-etl init-db

generate-sales-data --date 2026-01-15 --rows 100 --seed 42
daily-sales-etl run --input data/incoming/sales_20260115.csv
daily-sales-etl run --input data/incoming/sales_20260115.csv
```

The Compose container applies the schema automatically on a new volume; `init-db` is safe to run again and is useful for an existing volume. Input and quarantine CSVs are intentionally ignored by Git.

Verify the two runs and stable sales count:

```bash
docker compose exec postgres psql -U sales_app -d sales -c \
  "SELECT COUNT(*) AS sales_count FROM sales;"

docker compose exec postgres psql -U sales_app -d sales -c \
  "SELECT status, input_count, loaded_count, rejected_count, duration_seconds FROM etl_runs ORDER BY started_at;"
```

For a 100-row generated file, the expected local result is 100 sales rows, with `loaded_count` values of 100 and 0 for the first and second successful runs. This is an expected result, not a measurement from the development environment described below.

Exit codes are `0` for success, `2` for configuration/input errors, `3` for PostgreSQL errors, and `1` for unexpected failures. Logs go to standard error and include the run ID and counts.

## Tests

Fast tests use in-memory repository and connection test doubles. They cover cleaning, duplicate quarantine, malformed schema, load rollback behavior, durable failed audits, deterministic generation, and repeated runs:

```bash
pytest -m "not integration"
```

The real PostgreSQL test applies the schema, runs the same file twice, and asserts three database rows and audit `loaded_count` values of 3 then 0:

```bash
export TEST_DATABASE_URL="$DATABASE_URL"
pytest -m integration -v
```

GitHub Actions runs the complete suite against a PostgreSQL 16 service. This is a mocked-vs-real distinction: the fast tests mock repository/database behavior; the integration test and local Compose commands use a real PostgreSQL server.

## Verified results

Verified on November 5, 2026 with Python 3.12.16:

- `pytest -q --cov=daily_sales_etl --cov-report=term-missing`: **9 passed, 1 skipped**, 63% statement coverage. The skipped test was the opt-in PostgreSQL integration test because `TEST_DATABASE_URL` was not set.
- The 10-row generator was executed twice with date `2026-01-15` and seed `42`; both files had SHA-256 `4DF473223F7DEC156DAD41EC8F736C458980A452BD0AA307BF775E1825FD2B38` on this Windows environment.
- Starting the CLI without `DATABASE_URL` returned the documented input/configuration exit code `2`.

Docker and PostgreSQL were not installed in the development environment, so the Compose startup, real database integration test, and two-run database counts were not locally verified. The CI workflow is included to perform that verification after publishing.

## Daily scheduling example

Cron does not load an interactive shell, so use absolute paths and set the connection string explicitly. This example runs at 02:10 every day and expects the upstream file to use the current date:

```cron
10 2 * * * DATABASE_URL='postgresql://sales_app:local-password@localhost:5432/sales' /opt/daily-sales-etl/.venv/bin/daily-sales-etl run --input /opt/daily-sales-etl/data/incoming/sales_$(date +\%Y\%m\%d).csv --quarantine-dir /opt/daily-sales-etl/data/quarantine >> /var/log/daily-sales-etl.log 2>&1
```

Use a secret manager or protected environment file instead of embedding a production password in a real crontab.

## Cleanup

Stop containers while keeping data:

```bash
docker compose down
```

Remove containers and the local PostgreSQL volume (destructive):

```bash
docker compose down --volumes
```

This project does not provision AWS resources. There is no AWS deployment, IAM policy, cloud cost, or AWS cleanup step to report. Docker Compose is local-only and uses standard PostgreSQL credentials from environment variables; no credentials or secrets are committed.

## Limitations

- It processes one local file per command and does not discover or archive inputs.
- Row-by-row inserts favor readability over bulk-load throughput.
- Currency codes are format-checked but not checked against an ISO currency reference table.
- A file can be rerun safely, but there is no checksum-based prevention of changed content reusing an existing transaction ID.
- Quarantine files are local; production systems would usually store them in durable object storage.

## Interview questions and answers

1. **Why is the load idempotent?** `transaction_id` is a database primary key and inserts use `ON CONFLICT DO NOTHING`, so an already-loaded transaction cannot create another row.
2. **Why are audit writes separate from the sales transaction?** A failed sales transaction must roll back, but its failure record should survive for operations and debugging.
3. **Why use `Decimal` for price?** Binary floating-point cannot represent many decimal currency values exactly. `Decimal` plus PostgreSQL `NUMERIC(12,2)` gives predictable rounding and storage.
4. **What would change for millions of rows?** Stream the input in chunks, stage with PostgreSQL `COPY`, validate in SQL, merge set-wise, and track chunk or file checkpoints.
5. **How would you make file ingestion exactly-once?** Store a source-system file ID and content checksum under a unique constraint, claim it transactionally, and reject changed or previously completed files before loading rows.
