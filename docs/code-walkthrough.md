# Code walkthrough

A plain-language guide for explaining this project in an interview.

## The flow in one sentence

`__main__.py` reads your command, `bybit.py` **extracts** the candles, `quality.py` **checks** them, `store.py` **loads** them into SQLite, and `analytics.sql` **analyzes** them. That's the classic **ETL** pattern: Extract, Transform/validate, Load.

## `pipeline/bybit.py`: Extract

- **`build_url`** assembles the request, e.g. `https://api.bybit.com/v5/market/kline?category=linear&symbol=BTCUSDT&interval=D&limit=1000`. `category=linear` means USDT-settled perpetual contracts.
- **`fetch_json`** downloads and decodes the response. If the server says *"too many requests"* (HTTP 429) or has a temporary error (5xx), it waits 1 s, then 2 s, then 4 s and tries again. That's **exponential backoff**. Permanent errors (like a wrong symbol) fail straight away.
- **`parse_klines`** checks Bybit's own success code (`retCode == 0`), converts each row of text values into numbers, and sorts **oldest first**. Bybit sends newest first.
- **`fetch_range`** handles **pagination**. Bybit gives at most 1,000 candles per request, so to get 2,500 days the code asks for the newest 1,000, then the 1,000 before those, and so on. Results go into a dictionary keyed by time, so a candle that appears on two pages is stored once. The `fetch` parameter lets the tests plug in a fake API.

## `pipeline/quality.py`: Validate

Returns a list of problems in plain English:
- impossible candles (high below the close, low above the open, zero or negative prices, negative volume)
- **gaps**: the time between two candles should be exactly one interval (e.g. 86,400,000 ms for a day). If it's bigger, candles are missing, and the message says how many.

With `--strict`, any problem stops the load, so nothing half-checked reaches the database.

## `pipeline/store.py`: Load

- **`connect`** opens the database, creates the tables if needed, and registers a `sqrt` function, because not every SQLite build includes one and the volatility query needs it.
- **`upsert_candles`** is the key idea of the project: **"insert, or update if it already exists"** (`ON CONFLICT … DO UPDATE`). Running the same load twice gives the same result. That's called **idempotent**. It matters because the newest candle is still changing while its period is open. Everything runs in **one transaction**: either all rows are saved or none are. Each load is also logged in `ingestion_runs`.
- **`load_queries`** splits `analytics.sql` into named queries using the `-- name: …` markers, so the SQL stays in a `.sql` file where analysts can read it.

## `sql/analytics.sql`: Analyze

| Query | SQL idea it shows |
|---|---|
| `daily_returns` | `LAG(close)` looks at the previous row, so return = today ÷ yesterday − 1 |
| `moving_averages` | `AVG(close) OVER (ROWS BETWEEN 6 PRECEDING AND CURRENT ROW)` = 7-day average |
| `summary` | A CTE (`WITH …`) plus aggregates for first/last close, best/worst day |
| `volatility` | Standard deviation computed in SQL: √(average of squares − square of average) |
| `max_drawdown` | `MAX(close) OVER (ROWS UNBOUNDED PRECEDING)` = the highest price so far; the biggest fall below it is the drawdown |
| `volume_by_weekday` | `GROUP BY` on `strftime('%w', …)` |

## The tests

`tests/test_pipeline.py` checks parsing of Bybit's real format, paging 2,500 candles through a fake API (exactly 3 calls, no duplicates), quality checks, idempotent loading, and that every SQL query runs. One test uses three closes, 100 → 110 → 99, where the answers are easy to check by hand: returns of +10% and −10%, volatility 10%, drawdown −10%.

## Likely interview questions

- **"What happens if the job fails halfway?"** Each load is a single transaction, so nothing partial is saved. Just run it again, and the upsert makes that safe.
- **"How would you scale it?"** Same extract and validate code on a schedule in the cloud, raw responses saved to S3 for replay, and PostgreSQL/TimescaleDB instead of SQLite (ARCHITECTURE.md §3).
- **"Why not WebSockets?"** This is analytics on closed candles, so REST is simpler and easy to backfill. WebSockets are for live use (ADR-003).
- **"Why floats for prices?"** Fine for statistics, but never for money owed. Accounting would use decimal types (ADR-004).
