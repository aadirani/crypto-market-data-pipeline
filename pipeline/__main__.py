"""Command line: `python -m pipeline ingest ...` and `python -m pipeline report ...`."""

import argparse
import json
import sys
import time

from . import bybit, quality, store


def ingest(args):
    if args.from_file:
        with open(args.from_file, encoding="utf-8") as f:
            candles = bybit.parse_klines(json.load(f))
        source = f"file:{args.from_file}"
    else:
        end_ms = int(time.time() * 1000)
        start_ms = end_ms - args.days * 86_400_000
        candles = bybit.fetch_range(args.symbol, args.interval, start_ms, end_ms)
        source = "bybit-api"

    problems = quality.check_candles(candles, args.interval)
    for p in problems:
        print(f"quality: {p}", file=sys.stderr)
    if problems and args.strict:
        sys.exit("refusing to load: data-quality problems found (drop --strict to load anyway)")

    conn = store.connect(args.db)
    n = store.upsert_candles(conn, args.symbol, args.interval, candles, source)
    total = conn.execute("SELECT COUNT(*) FROM candles WHERE symbol = ? AND interval = ?",
                         (args.symbol, args.interval)).fetchone()[0]
    print(f"loaded {n} candles from {source}; {total} stored for {args.symbol} {args.interval}")


def print_table(rows):
    if not rows:
        print("(no rows)\n")
        return
    headers = list(rows[0])
    print("| " + " | ".join(headers) + " |")
    print("|" + "---|" * len(headers))
    for row in rows:
        print("| " + " | ".join("" if v is None else str(v) for v in row.values()) + " |")
    print()


def report(args):
    conn = store.connect(args.db)
    queries = store.load_queries()
    names = args.query or ["summary", "volatility", "max_drawdown", "volume_by_weekday"]
    for name in names:
        rows = store.run_query(conn, queries[name], symbol=args.symbol, interval=args.interval)
        print(f"### {name}\n")
        print_table(rows[-args.tail:] if args.tail else rows)


def main(argv=None):
    p = argparse.ArgumentParser(prog="pipeline", description=__doc__)
    sub = p.add_subparsers(dest="command", required=True)

    i = sub.add_parser("ingest", help="download candles and load them into SQLite")
    i.add_argument("--symbol", default="BTCUSDT")
    i.add_argument("--interval", default="D", choices=sorted(bybit.INTERVAL_MS) + ["M"])
    i.add_argument("--days", type=int, default=365, help="how far back to download")
    i.add_argument("--db", default="market.db")
    i.add_argument("--from-file", help="load a saved API response instead of calling Bybit")
    i.add_argument("--strict", action="store_true", help="stop if any quality check fails")
    i.set_defaults(func=ingest)

    r = sub.add_parser("report", help="run SQL analytics and print Markdown tables")
    r.add_argument("--symbol", default="BTCUSDT")
    r.add_argument("--interval", default="D")
    r.add_argument("--db", default="market.db")
    r.add_argument("--query", action="append", help="query name from sql/analytics.sql (repeatable)")
    r.add_argument("--tail", type=int, default=0, help="only show the last N rows of each result")
    r.set_defaults(func=report)

    args = p.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
