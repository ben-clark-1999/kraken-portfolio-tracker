-- OHLC price cache: avoids redundant Kraken API calls for historical daily candles.
-- Used by get_buy_and_hold_comparison and get_relative_performance tools.
CREATE TABLE IF NOT EXISTS ohlc_cache (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    pair TEXT NOT NULL,
    date TEXT NOT NULL,
    close_price NUMERIC NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (pair, date)
);

CREATE INDEX IF NOT EXISTS idx_ohlc_cache_pair ON ohlc_cache (pair);
