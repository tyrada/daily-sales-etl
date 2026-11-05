CREATE TABLE IF NOT EXISTS sales (
    transaction_id TEXT PRIMARY KEY,
    sale_date DATE NOT NULL,
    customer_id TEXT NOT NULL,
    product_id TEXT NOT NULL,
    quantity INTEGER NOT NULL CHECK (quantity > 0),
    unit_price NUMERIC(12, 2) NOT NULL CHECK (unit_price > 0),
    currency CHAR(3) NOT NULL CHECK (currency ~ '^[A-Z]{3}$'),
    source_file TEXT NOT NULL,
    loaded_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS etl_runs (
    run_id UUID PRIMARY KEY,
    source_file TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('RUNNING', 'SUCCEEDED', 'FAILED')),
    started_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    finished_at TIMESTAMPTZ,
    duration_seconds NUMERIC(12, 3),
    input_count INTEGER NOT NULL DEFAULT 0 CHECK (input_count >= 0),
    loaded_count INTEGER NOT NULL DEFAULT 0 CHECK (loaded_count >= 0),
    rejected_count INTEGER NOT NULL DEFAULT 0 CHECK (rejected_count >= 0),
    error_message TEXT
);

CREATE INDEX IF NOT EXISTS idx_etl_runs_started_at ON etl_runs (started_at DESC);

