import json
import unittest
from pathlib import Path

from pipeline import bybit, quality, store

ROOT = Path(__file__).resolve().parent.parent
FIXTURE = ROOT / "data" / "sample_kline_BTCUSDT_D.json"
DAY = 86_400_000


def candle(t, o, h, l, c, v=1.0):
    return {"open_time": t, "open": o, "high": h, "low": l, "close": c, "volume": v, "turnover": v * c}


def bybit_payload(rows):
    """Build a response in Bybit's format: string fields, newest first."""
    newest_first = sorted(rows, key=lambda r: -r["open_time"])
    return {"retCode": 0, "retMsg": "OK", "result": {"list": [
        [str(r["open_time"]), str(r["open"]), str(r["high"]), str(r["low"]),
         str(r["close"]), str(r["volume"]), str(r["turnover"])] for r in newest_first]}}


class ParseTests(unittest.TestCase):
    def test_fixture_parses_oldest_first(self):
        candles = bybit.parse_klines(json.loads(FIXTURE.read_text(encoding="utf-8")))
        self.assertEqual(len(candles), 120)
        self.assertLess(candles[0]["open_time"], candles[-1]["open_time"])
        self.assertIsInstance(candles[0]["close"], float)

    def test_api_error_raises(self):
        with self.assertRaises(ValueError):
            bybit.parse_klines({"retCode": 10001, "retMsg": "params error"})

    def test_build_url(self):
        url = bybit.build_url("ETHUSDT", "60", start_ms=1, end_ms=2)
        self.assertIn("symbol=ETHUSDT", url)
        self.assertIn("interval=60", url)
        self.assertIn("start=1", url)


class PaginationTests(unittest.TestCase):
    def test_fetch_range_pages_backwards_without_duplicates(self):
        all_rows = [candle(i * DAY, 1, 2, 0.5, 1.5) for i in range(2500)]
        calls = []

        def fake_fetch(url):
            params = dict(p.split("=") for p in url.split("?")[1].split("&"))
            start, end = int(params["start"]), int(params["end"])
            calls.append(end)
            window = [r for r in all_rows if start <= r["open_time"] <= end][-bybit.MAX_LIMIT:]
            return bybit_payload(window)

        result = bybit.fetch_range("BTCUSDT", "D", 0, 2499 * DAY, fetch=fake_fetch, pause=0)
        self.assertEqual(len(result), 2500)
        self.assertEqual(len(calls), 3)  # 1000 + 1000 + 500
        self.assertEqual([c["open_time"] for c in result], sorted(c["open_time"] for c in result))


class QualityTests(unittest.TestCase):
    def test_clean_fixture(self):
        candles = bybit.parse_klines(json.loads(FIXTURE.read_text(encoding="utf-8")))
        self.assertEqual(quality.check_candles(candles, "D"), [])

    def test_detects_bad_high_and_gap(self):
        candles = [candle(0, 10, 9, 8, 9.5), candle(3 * DAY, 10, 11, 9, 10)]
        problems = quality.check_candles(candles, "D")
        self.assertTrue(any("high is below" in p for p in problems))
        self.assertTrue(any("gap of 2" in p for p in problems))


class StoreAndAnalyticsTests(unittest.TestCase):
    def setUp(self):
        self.conn = store.connect(":memory:")
        self.queries = store.load_queries()

    def count(self):
        return self.conn.execute("SELECT COUNT(*) FROM candles").fetchone()[0]

    def test_upsert_is_idempotent(self):
        rows = [candle(i * DAY, 100, 110, 90, 105) for i in range(5)]
        store.upsert_candles(self.conn, "BTCUSDT", "D", rows, "test")
        store.upsert_candles(self.conn, "BTCUSDT", "D", rows, "test")
        self.assertEqual(self.count(), 5)
        runs = self.conn.execute("SELECT COUNT(*) FROM ingestion_runs").fetchone()[0]
        self.assertEqual(runs, 2)

    def test_upsert_updates_changed_candle(self):
        store.upsert_candles(self.conn, "BTCUSDT", "D", [candle(0, 100, 110, 90, 105)], "test")
        store.upsert_candles(self.conn, "BTCUSDT", "D", [candle(0, 100, 120, 90, 115)], "test")
        close = self.conn.execute("SELECT close FROM candles").fetchone()[0]
        self.assertEqual(close, 115)

    def test_all_queries_run_on_fixture(self):
        candles = bybit.parse_klines(json.loads(FIXTURE.read_text(encoding="utf-8")))
        store.upsert_candles(self.conn, "BTCUSDT", "D", candles, "fixture")
        for name, sql in self.queries.items():
            with self.subTest(query=name):
                self.assertTrue(store.run_query(self.conn, sql, symbol="BTCUSDT", interval="D"))

    def test_returns_volatility_and_drawdown_by_hand(self):
        # Closes 100 -> 110 -> 99: returns +10 % and -10 %.
        rows = [candle(0, 100, 100, 100, 100), candle(DAY, 100, 110, 100, 110),
                candle(2 * DAY, 110, 110, 99, 99)]
        store.upsert_candles(self.conn, "X", "D", rows, "test")
        q = lambda name: store.run_query(self.conn, self.queries[name], symbol="X", interval="D")

        self.assertEqual([r["return_pct"] for r in q("daily_returns")], [None, 10.0, -10.0])
        # mean 0, mean of squares 0.01 -> standard deviation 0.1 = 10 %
        self.assertEqual(q("volatility")[0]["volatility_pct"], 10.0)
        # peak 110, trough 99 -> -10 %
        self.assertEqual(q("max_drawdown")[0]["max_drawdown_pct"], -10.0)
        self.assertEqual(q("summary")[0]["change_pct"], -1.0)


if __name__ == "__main__":
    unittest.main()
