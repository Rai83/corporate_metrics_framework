from sqlalchemy import create_engine, text
import pandas as pd
from typing import Optional
import os
from dotenv import load_dotenv

load_dotenv()

DB_CONFIG = {
    "host":     os.getenv("DB_HOST", "localhost"),
    "port":     int(os.getenv("DB_PORT", 5432)),
    "database": os.getenv("DB_NAME", "corporate_metrics"),
    "user":     os.getenv("DB_USER", "corporate_metrics_user"),
    "password": os.getenv("DB_PASSWORD")
}


def build_engine(config=None):
    if config is None:
        config = DB_CONFIG
    url = (
        f"postgresql+psycopg2://{config['user']}:{config['password']}"
        f"@{config['host']}:{config['port']}/{config['dbname']}"
    )
    return create_engine(url, pool_pre_ping=True)


class MarketPricesClient:

    def __init__(self, config=None):
        if config is None:
            config = DB_CONFIG
        self.engine        = build_engine(config)
        self._series_cache = {}

    # ══════════════════════════════════════════════════════════════════════════
    # price_series — catálogo
    # ══════════════════════════════════════════════════════════════════════════

    def get_series_catalog(self) -> pd.DataFrame:
        with self.engine.connect() as conn:
            return pd.read_sql(
                text("SELECT * FROM price_series ORDER BY company, category"),
                conn
            )

    def get_series_id(self, code: str) -> int:
        if code not in self._series_cache:
            with self.engine.connect() as conn:
                row = conn.execute(
                    text("SELECT id FROM price_series WHERE code = :code"),
                    {"code": code}
                ).fetchone()
                if not row:
                    raise ValueError(f"Serie '{code}' no encontrada en price_series.")
                self._series_cache[code] = row[0]
        return self._series_cache[code]

    def add_series(
        self, code: str, name: str, category: str,
        unit: str, currency: str = None, source: str = None,
        source_code: str = None, company: str = None,
        description: str = None
    ) -> int:
        with self.engine.begin() as conn:
            row = conn.execute(text("""
                INSERT INTO price_series
                    (code, name, category, unit, currency,
                     source, source_code, company, description)
                VALUES (:code,:name,:category,:unit,:currency,
                        :source,:source_code,:company,:description)
                ON CONFLICT (code) DO NOTHING
                RETURNING id
            """), {
                "code": code, "name": name, "category": category,
                "unit": unit, "currency": currency, "source": source,
                "source_code": source_code, "company": company,
                "description": description
            }).fetchone()

        series_id = row[0] if row else self.get_series_id(code)
        print(f"ADD SERIES: '{code}' → id={series_id}")
        return series_id

    # ══════════════════════════════════════════════════════════════════════════
    # market_prices — SELECT
    # ══════════════════════════════════════════════════════════════════════════

    def select(
        self,
        codes:   Optional[list] = None,
        start:   Optional[str]  = None,
        end:     Optional[str]  = None,
        company: Optional[str]  = None,
        pivot:   bool           = True,
    ) -> pd.DataFrame:
        query = """
            SELECT
                mp.time,
                ps.code,
                ps.company,
                ps.category,
                mp.value
            FROM market_prices mp
            JOIN price_series ps ON ps.id = mp.series_id
            WHERE 1=1
        """
        params = {}

        if codes:
            query += " AND ps.code = ANY(:codes)"
            params["codes"] = codes
        if start:
            query += " AND mp.time >= :start"
            params["start"] = start
        if end:
            query += " AND mp.time <= :end"
            params["end"] = end
        if company:
            query += " AND ps.company IN (:company, 'BOTH')"
            params["company"] = company

        query += " ORDER BY mp.time DESC, ps.code"

        with self.engine.connect() as conn:
            df = pd.read_sql(text(query), conn, params=params,
                             parse_dates=["time"])

        if pivot and not df.empty:
            df = df.pivot_table(
                index="time", columns="code",
                values="value", aggfunc="first"
            )
            df.columns.name = None
            df = df.sort_index()

        return df

    def select_latest(self, n: int = 10, codes: list = None) -> pd.DataFrame:
        df = self.select(codes=codes, pivot=False)
        if df.empty:
            return df
        latest_dates = df["time"].drop_duplicates().nlargest(n)
        return df[df["time"].isin(latest_dates)]

    # ══════════════════════════════════════════════════════════════════════════
    # market_prices — INSERT / UPSERT
    # ══════════════════════════════════════════════════════════════════════════

    def _df_to_long(self, df: pd.DataFrame) -> list[dict]:
        rows = []
        for ts, row in df.iterrows():
            for code, value in row.items():
                if code == "source" or pd.isna(value):
                    continue
                rows.append({
                    "time"     : ts,
                    "series_id": self.get_series_id(code),
                    "value"    : float(value)
                })
        return rows

    def insert(self, df: pd.DataFrame) -> int:
        rows = self._df_to_long(df)
        with self.engine.begin() as conn:
            conn.execute(text("""
                INSERT INTO market_prices (time, series_id, value)
                VALUES (:time, :series_id, :value)
                ON CONFLICT DO NOTHING
            """), rows)
        print(f"INSERT: {len(rows)} filas procesadas.")
        return len(rows)

    def upsert(self, df: pd.DataFrame) -> int:
        rows = self._df_to_long(df)
        with self.engine.begin() as conn:
            conn.execute(text("""
                INSERT INTO market_prices (time, series_id, value)
                VALUES (:time, :series_id, :value)
                ON CONFLICT (time, series_id) DO UPDATE
                    SET value = EXCLUDED.value
            """), rows)
        print(f"UPSERT: {len(rows)} filas procesadas.")
        return len(rows)

    # ══════════════════════════════════════════════════════════════════════════
    # market_prices — UPDATE / DELETE
    # ══════════════════════════════════════════════════════════════════════════

    def update(self, time: str, code: str, value: float) -> int:
        series_id = self.get_series_id(code)
        with self.engine.begin() as conn:
            result = conn.execute(text("""
                UPDATE market_prices SET value = :value
                WHERE time = :time AND series_id = :series_id
            """), {"value": value, "time": time, "series_id": series_id})
        print(f"UPDATE: {result.rowcount} fila(s) — {code} en {time} → {value}")
        return result.rowcount

    def delete_by_date(self, time: str, code: str = None) -> int:
        with self.engine.begin() as conn:
            if code:
                series_id = self.get_series_id(code)
                result = conn.execute(text("""
                    DELETE FROM market_prices
                    WHERE time = :time AND series_id = :series_id
                """), {"time": time, "series_id": series_id})
            else:
                result = conn.execute(
                    text("DELETE FROM market_prices WHERE time = :time"),
                    {"time": time}
                )
        print(f"DELETE: {result.rowcount} fila(s) eliminadas.")
        return result.rowcount

    def delete_range(self, start: str, end: str, code: str = None) -> int:
        with self.engine.begin() as conn:
            if code:
                series_id = self.get_series_id(code)
                result = conn.execute(text("""
                    DELETE FROM market_prices
                    WHERE time BETWEEN :start AND :end
                    AND series_id = :series_id
                """), {"start": start, "end": end, "series_id": series_id})
            else:
                result = conn.execute(text("""
                    DELETE FROM market_prices
                    WHERE time BETWEEN :start AND :end
                """), {"start": start, "end": end})
        print(f"DELETE: {result.rowcount} fila(s) eliminadas entre {start} y {end}.")
        return result.rowcount

    # ══════════════════════════════════════════════════════════════════════════
    # UTILIDADES
    # ══════════════════════════════════════════════════════════════════════════

    def summary(self) -> None:
        with self.engine.connect() as conn:
            df = pd.read_sql(text("""
                SELECT
                    ps.code,
                    ps.company,
                    ps.category,
                    ps.unit,
                    COUNT(mp.value)                  AS n,
                    MIN(mp.time)                     AS desde,
                    MAX(mp.time)                     AS hasta,
                    ROUND(AVG(mp.value)::numeric, 4) AS media
                FROM price_series ps
                LEFT JOIN market_prices mp ON mp.series_id = ps.id
                GROUP BY ps.id, ps.code, ps.company, ps.category, ps.unit
                ORDER BY ps.company, ps.category
            """), conn)
        print("\n── market_prices summary ─────────────────────────────")
        print(df.to_string(index=False))

    def execute(self, query: str, params: dict = None) -> pd.DataFrame:
        with self.engine.connect() as conn:
            return pd.read_sql(text(query), conn, params=params)
