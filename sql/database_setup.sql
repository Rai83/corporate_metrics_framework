-- ══════════════════════════════════════════════════════════════════════════════
-- CORPORATE METRICS — TimescaleDB setup
-- ══════════════════════════════════════════════════════════════════════════════

-- ── 1. Extensión TimescaleDB ──────────────────────────────────────────────────
CREATE EXTENSION IF NOT EXISTS timescaledb CASCADE;

-- ── 2. Crear usuario ──────────────────────────────────────────────────────────
CREATE USER corporate_metrics_user WITH PASSWORD 'cm_password_2024';

-- ── 3. Crear base de datos ────────────────────────────────────────────────────
CREATE DATABASE corporate_metrics OWNER corporate_metrics_user;

-- ── (conectar a corporate_metrics antes de continuar) ────────────────────────
-- \c corporate_metrics

-- ══════════════════════════════════════════════════════════════════════════════
-- TABLA 1 — price_series: catálogo de tipos de precio
-- ══════════════════════════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS price_series (
    id          SERIAL          PRIMARY KEY,
    code        TEXT            NOT NULL UNIQUE,    -- ej. 'jet_fuel', 'eur_usd'
    name        TEXT            NOT NULL,           -- ej. 'Jet Fuel US Gulf Coast'
    category    TEXT            NOT NULL,           -- 'commodity' | 'fx' | 'rate'
    unit        TEXT            NOT NULL,           -- ej. 'USD/gallon', 'EUR/USD'
    currency    TEXT,                               -- 'USD', 'EUR', etc.
    source      TEXT,                               -- 'FRED', 'WorldBank', 'Yahoo'
    source_code TEXT,                               -- ej. 'WJFUELUSGULF'
    company     TEXT,                               -- 'IAG' | 'EBRO' | 'BOTH'
    description TEXT,
    created_at  TIMESTAMPTZ     DEFAULT NOW()
);

-- ══════════════════════════════════════════════════════════════════════════════
-- TABLA 2 — market_prices: precios con FK a price_series
-- ══════════════════════════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS market_prices (
    time        TIMESTAMPTZ     NOT NULL,
    series_id   INTEGER         NOT NULL REFERENCES price_series(id)
                                ON DELETE RESTRICT,
    value       DOUBLE PRECISION NOT NULL,
    created_at  TIMESTAMPTZ     DEFAULT NOW(),

    CONSTRAINT market_prices_pkey PRIMARY KEY (time, series_id)
);

-- ── Convertir a hypertable ────────────────────────────────────────────────────
SELECT create_hypertable(
    'market_prices',
    'time',
    if_not_exists => TRUE,
    migrate_data  => TRUE
);

-- ── Índices ───────────────────────────────────────────────────────────────────
CREATE INDEX IF NOT EXISTS idx_market_prices_time
    ON market_prices (time DESC);

CREATE INDEX IF NOT EXISTS idx_market_prices_series
    ON market_prices (series_id, time DESC);

-- ── Permisos ──────────────────────────────────────────────────────────────────
GRANT CONNECT  ON DATABASE corporate_metrics       TO corporate_metrics_user;
GRANT USAGE    ON SCHEMA public                    TO corporate_metrics_user;
GRANT SELECT, INSERT, UPDATE, DELETE
    ON ALL TABLES IN SCHEMA public                 TO corporate_metrics_user;
GRANT USAGE, SELECT
    ON ALL SEQUENCES IN SCHEMA public              TO corporate_metrics_user;

ALTER DEFAULT PRIVILEGES IN SCHEMA public
    GRANT SELECT, INSERT, UPDATE, DELETE
    ON TABLES TO corporate_metrics_user;

-- ══════════════════════════════════════════════════════════════════════════════
-- DATOS INICIALES — catálogo de series
-- ══════════════════════════════════════════════════════════════════════════════
INSERT INTO price_series
    (code, name, category, unit, currency, source, source_code, company, description)
VALUES
    -- IAG
    ('jet_fuel',     'Jet Fuel US Gulf Coast',       'commodity', 'USD/gallon',    'USD', 'FRED',       'WJFUELUSGULF',  'IAG',  'Weekly jet fuel spot price, US Gulf Coast'),
    ('eur_usd',      'EUR/USD Exchange Rate',         'fx',        'EUR/USD',       'USD', 'Yahoo',      'EURUSD=X',      'BOTH', 'Euro to US Dollar exchange rate'),
    ('eur_gbp',      'EUR/GBP Exchange Rate',         'fx',        'EUR/GBP',       'GBP', 'Yahoo',      'EURGBP=X',      'IAG',  'Euro to British Pound exchange rate'),
    -- EBRO
    ('rice_thai5',   'Rice Thai 5% Broken',           'commodity', 'USD/mt',        'USD', 'WorldBank',  'CMO-Pink',      'EBRO', 'Thai white rice 5% broken, FOB Bangkok'),
    ('durum_wheat',  'Durum Wheat PPI USA',           'commodity', 'Index 1982=100','USD', 'FRED',       'WPU01210105',   'EBRO', 'Producer Price Index for Hard Amber Durum Wheat'),
    ('wheat_global', 'Wheat Global Price USD/mt',     'commodity', 'USD/mt',        'USD', 'FRED',       'PWHEAMTUSDM',   'EBRO', 'Global wheat price, US$/metric ton')
ON CONFLICT (code) DO NOTHING;

-- ── Verificación ──────────────────────────────────────────────────────────────
SELECT id, code, category, unit, company, source
FROM price_series
ORDER BY company, category;