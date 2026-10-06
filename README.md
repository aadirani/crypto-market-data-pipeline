# Crypto Market Data Pipeline

![tests](https://github.com/aadirani/crypto-market-data-pipeline/actions/workflows/tests.yml/badge.svg)

Download price candles from **Bybit's public API**, check them, store them in **SQL**, and analyze them with **SQL window functions**, using only Python's standard library.

## The idea in one paragraph

A "candle" summarizes trading over a period (a minute, an hour, a day): the opening, highest, lowest and closing price, plus how much was traded. This pipeline downloads candles for any symbol (like `BTCUSDT`), runs **quality checks** (no impossible prices, no missing days), saves them into a database in a way that's **safe to re-run**, and answers questions like *"What was the biggest drop from a peak?"* or *"How volatile was it?"* with plain SQL.

No API key and no account are needed, and it never places trades.

## Quick start

Needs Python 3.9+. Nothing to install.

```bash
# Real data (from a country where Bybit's API is available)
python -m pipeline ingest --symbol BTCUSDT --interval D --days 365
python -m pipeline report

# Offline, using the bundled synthetic sample
python -m pipeline ingest --from-file data/sample_kline_BTCUSDT_D.json --db demo.db --strict
python -m pipeline report --db demo.db
python -m pipeline report --db demo.db --query moving_averages --tail 5
```

The report prints Markdown tables: a summary of the period, volatility, maximum drawdown and average volume by weekday.

## What's inside

| Path | What it is |
|---|---|
| [ARCHITECTURE.md](ARCHITECTURE.md) | Design, diagrams, 6 decision records, risks, costs, target cloud design |
| [pipeline/bybit.py](pipeline/bybit.py) | Extract: API calls, paging, retries |
| [pipeline/quality.py](pipeline/quality.py) | Data-quality checks |
| [pipeline/store.py](pipeline/store.py) | Load: idempotent upsert into SQLite, audit table |
| [sql/schema.sql](sql/schema.sql) · [sql/analytics.sql](sql/analytics.sql) | Tables and the analytics queries |
| [docs/code-walkthrough.md](docs/code-walkthrough.md) | Plain-language explanation of the code and SQL |
| [data/sample_kline_BTCUSDT_D.json](data/sample_kline_BTCUSDT_D.json) | **Synthetic** sample in Bybit's exact response format (not real prices) |

## Good to know

- **Bybit isn't available in every country**, including the US, where GitHub's test servers run. That's why the automated tests use the synthetic sample file. Check that using the API is permitted where you run it.
- This is a data-engineering project. Its statistics describe the past and are **not trading advice**.

---

Built with AI assistance.
