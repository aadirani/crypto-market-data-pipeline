-- Analytics queries. Each starts with "-- name: <name>" so the Python code can find it.
-- All take two parameters: :symbol and :interval.

-- name: daily_returns
-- Percentage change from the previous candle's close (LAG looks one row back).
SELECT
    date(open_time / 1000, 'unixepoch') AS day,
    close,
    ROUND(100.0 * (close / LAG(close) OVER w - 1), 2) AS return_pct
FROM candles
WHERE symbol = :symbol AND interval = :interval
WINDOW w AS (ORDER BY open_time)
ORDER BY open_time;

-- name: moving_averages
-- 7- and 30-candle simple moving averages using window frames.
SELECT
    date(open_time / 1000, 'unixepoch') AS day,
    close,
    ROUND(AVG(close) OVER (ORDER BY open_time ROWS BETWEEN 6 PRECEDING AND CURRENT ROW), 1) AS sma_7,
    ROUND(AVG(close) OVER (ORDER BY open_time ROWS BETWEEN 29 PRECEDING AND CURRENT ROW), 1) AS sma_30
FROM candles
WHERE symbol = :symbol AND interval = :interval
ORDER BY open_time;

-- name: summary
-- One-row overview of the whole stored period.
WITH ordered AS (
    SELECT *, close / LAG(close) OVER (ORDER BY open_time) - 1 AS ret
    FROM candles
    WHERE symbol = :symbol AND interval = :interval
)
SELECT
    COUNT(*)                                                            AS candles,
    date(MIN(open_time) / 1000, 'unixepoch')                            AS first_day,
    date(MAX(open_time) / 1000, 'unixepoch')                            AS last_day,
    (SELECT close FROM ordered ORDER BY open_time LIMIT 1)              AS first_close,
    (SELECT close FROM ordered ORDER BY open_time DESC LIMIT 1)         AS last_close,
    ROUND(100.0 * ((SELECT close FROM ordered ORDER BY open_time DESC LIMIT 1)
                 / (SELECT close FROM ordered ORDER BY open_time LIMIT 1) - 1), 2) AS change_pct,
    MAX(high)                                                           AS highest,
    MIN(low)                                                            AS lowest,
    ROUND(100.0 * MAX(ret), 2)                                          AS best_candle_pct,
    ROUND(100.0 * MIN(ret), 2)                                          AS worst_candle_pct,
    ROUND(AVG(volume), 1)                                               AS avg_volume
FROM ordered;

-- name: volatility
-- Standard deviation of candle returns: sqrt(average of squares - square of average).
WITH r AS (
    SELECT close / LAG(close) OVER (ORDER BY open_time) - 1 AS ret
    FROM candles
    WHERE symbol = :symbol AND interval = :interval
)
SELECT
    COUNT(ret)                                                   AS returns,
    ROUND(100.0 * sqrt(AVG(ret * ret) - AVG(ret) * AVG(ret)), 2) AS volatility_pct
FROM r
WHERE ret IS NOT NULL;

-- name: max_drawdown
-- Largest fall from a previous peak (running maximum via an unbounded window).
WITH peaks AS (
    SELECT
        open_time,
        close,
        MAX(close) OVER (ORDER BY open_time ROWS UNBOUNDED PRECEDING) AS peak
    FROM candles
    WHERE symbol = :symbol AND interval = :interval
)
SELECT
    ROUND(100.0 * MIN(close / peak - 1), 2)                                 AS max_drawdown_pct,
    (SELECT date(open_time / 1000, 'unixepoch') FROM peaks
      ORDER BY close / peak ASC LIMIT 1)                                    AS trough_day
FROM peaks;

-- name: volume_by_weekday
-- Average traded volume per day of the week (0 = Sunday).
SELECT
    CAST(strftime('%w', open_time / 1000, 'unixepoch') AS INTEGER) AS weekday,
    COUNT(*)                                                       AS candles,
    ROUND(AVG(volume), 1)                                          AS avg_volume
FROM candles
WHERE symbol = :symbol AND interval = :interval
GROUP BY weekday
ORDER BY weekday;
