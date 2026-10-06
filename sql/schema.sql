-- One row per candle. The primary key makes re-loading the same data safe (idempotent).
CREATE TABLE IF NOT EXISTS candles (
    symbol      TEXT    NOT NULL,
    interval    TEXT    NOT NULL,
    open_time   INTEGER NOT NULL,  -- candle start, Unix milliseconds, UTC
    open        REAL    NOT NULL,
    high        REAL    NOT NULL,
    low         REAL    NOT NULL,
    close       REAL    NOT NULL,
    volume      REAL    NOT NULL,  -- in the base coin (e.g. BTC)
    turnover    REAL    NOT NULL,  -- in the quote coin (e.g. USDT)
    ingested_at TEXT    NOT NULL,
    PRIMARY KEY (symbol, interval, open_time),
    CHECK (high >= low)
);

-- Audit trail: every load is recorded, so you can see where the data came from and when.
CREATE TABLE IF NOT EXISTS ingestion_runs (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    run_at        TEXT    NOT NULL,
    source        TEXT    NOT NULL,
    symbol        TEXT    NOT NULL,
    interval      TEXT    NOT NULL,
    rows_received INTEGER NOT NULL
);
