-- OHLC price cache: avoids redundant Kraken API calls for historical daily candles.
-- Used by get_ohlc_cached in portfolio_service (via ohlc_cache_repo).
-- Keyed by (pair, date) composite unique constraint; id is UUID PK for PostgREST compat.

CREATE TABLE IF NOT EXISTS public.ohlc_cache (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    pair TEXT NOT NULL,
    date TEXT NOT NULL,
    close_price NUMERIC NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (pair, date)
);

CREATE INDEX IF NOT EXISTS idx_ohlc_cache_pair ON public.ohlc_cache (pair);

-- Mirror in test schema for integration tests
CREATE TABLE IF NOT EXISTS test.ohlc_cache (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    pair TEXT NOT NULL,
    date TEXT NOT NULL,
    close_price NUMERIC NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (pair, date)
);

CREATE INDEX IF NOT EXISTS idx_test_ohlc_cache_pair ON test.ohlc_cache (pair);

GRANT ALL ON public.ohlc_cache TO anon, authenticated, service_role;
GRANT ALL ON test.ohlc_cache TO anon, authenticated, service_role;
