"""Extract: download candles (klines) from Bybit's public v5 market API.

Public market data needs no API key. Docs: https://bybit-exchange.github.io/docs/v5/market/kline
"""

import json
import time
import urllib.error
import urllib.parse
import urllib.request

BASE_URL = "https://api.bybit.com/v5/market/kline"
MAX_LIMIT = 1000  # Bybit returns at most 1000 candles per request

# Length of one candle in milliseconds. "M" (month) has no fixed length.
INTERVAL_MS = {
    "1": 60_000, "3": 180_000, "5": 300_000, "15": 900_000, "30": 1_800_000,
    "60": 3_600_000, "120": 7_200_000, "240": 14_400_000, "360": 21_600_000,
    "720": 43_200_000, "D": 86_400_000, "W": 604_800_000,
}


def build_url(symbol, interval, start_ms=None, end_ms=None, category="linear", limit=MAX_LIMIT):
    params = {"category": category, "symbol": symbol, "interval": interval, "limit": limit}
    if start_ms is not None:
        params["start"] = start_ms
    if end_ms is not None:
        params["end"] = end_ms
    return f"{BASE_URL}?{urllib.parse.urlencode(params)}"


def fetch_json(url, retries=3, timeout=15):
    """GET a URL and decode JSON, retrying with exponential backoff on temporary errors."""
    request = urllib.request.Request(url, headers={"User-Agent": "market-data-pipeline/1.0"})
    for attempt in range(retries + 1):
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                return json.load(response)
        except urllib.error.HTTPError as err:
            temporary = err.code == 429 or err.code >= 500
            if not temporary or attempt == retries:
                raise
        except urllib.error.URLError:
            if attempt == retries:
                raise
        time.sleep(2 ** attempt)  # 1 s, 2 s, 4 s ...


def parse_klines(payload):
    """Turn a Bybit response into a list of candle dicts, oldest first."""
    if payload.get("retCode") != 0:
        raise ValueError(f"Bybit error {payload.get('retCode')}: {payload.get('retMsg')}")
    candles = []
    for row in payload["result"]["list"]:
        start, open_, high, low, close, volume, turnover = row
        candles.append({
            "open_time": int(start),
            "open": float(open_), "high": float(high), "low": float(low), "close": float(close),
            "volume": float(volume), "turnover": float(turnover),
        })
    return sorted(candles, key=lambda c: c["open_time"])


def fetch_range(symbol, interval, start_ms, end_ms, fetch=fetch_json, pause=0.2):
    """Download every candle between start_ms and end_ms, paging backwards 1000 at a time.

    Bybit returns the newest candles first, so each page ends just before the
    oldest candle of the previous page. `fetch` can be replaced in tests.
    """
    candles = {}
    cursor = end_ms
    while cursor >= start_ms:
        page = parse_klines(fetch(build_url(symbol, interval, start_ms, cursor)))
        if not page:
            break
        for candle in page:
            candles[candle["open_time"]] = candle  # dict removes duplicates at page edges
        oldest = page[0]["open_time"]
        if oldest <= start_ms or len(page) < MAX_LIMIT:
            break
        cursor = oldest - 1
        time.sleep(pause)  # stay well inside the public rate limit
    return [candles[t] for t in sorted(candles)]
