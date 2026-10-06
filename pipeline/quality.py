"""Data-quality checks run on every batch before it is loaded."""

from .bybit import INTERVAL_MS


def check_candles(candles, interval):
    """Return a list of human-readable problems. An empty list means the batch is clean."""
    problems = []
    for c in candles:
        when = c["open_time"]
        if c["high"] < max(c["open"], c["close"]):
            problems.append(f"{when}: high is below open/close")
        if c["low"] > min(c["open"], c["close"]):
            problems.append(f"{when}: low is above open/close")
        if min(c["open"], c["high"], c["low"], c["close"]) <= 0:
            problems.append(f"{when}: non-positive price")
        if c["volume"] < 0:
            problems.append(f"{when}: negative volume")

    step = INTERVAL_MS.get(interval)
    if step:
        times = sorted(c["open_time"] for c in candles)
        for earlier, later in zip(times, times[1:]):
            if later - earlier != step:
                missing = (later - earlier) // step - 1
                problems.append(f"{earlier}: gap of {missing} candle(s) before {later}")
    return problems
