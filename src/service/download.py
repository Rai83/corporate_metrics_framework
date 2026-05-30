import os

import pandas as pd

from src.db.client import MarketPricesClient
from src.repository import yf_client
from src.repository.fred_client import download_by_ticker
from src.repository.world_bank_client import get_by_ticker

os.makedirs("data", exist_ok=True)

client = MarketPricesClient()

START = "2019-01-01"
END   = "2024-12-31"

jet_fuel = download_by_ticker("WJFUELUSGULF", "jet_fuel_usd_gal", START, END)
jet_fuel = jet_fuel.resample("1MS").mean()
jet_fuel.name = "jet_fuel"

durum = download_by_ticker("WPU01210105", "durum_wheat_ppi", START, END)
durum.name = "durum_wheat"

wheat = download_by_ticker("PWHEAMTUSDM", "wheat_usd_mt", START, END)
wheat.name = "wheat_global"

eur_usd_raw = yf_client.download_by_ticker(ticker="EURUSD=X", start=START, end=END)
eur_gbp_raw = yf_client.download_by_ticker(ticker="EURGBP=X", start=START, end=END)

eur_usd = yf_client.extract_close(eur_usd_raw, "EURUSD=X").resample("MS").mean()
eur_gbp = yf_client.extract_close(eur_gbp_raw, "EURGBP=X").resample("MS").mean()
eur_usd.name = "eur_usd"
eur_gbp.name = "eur_gbp"

rice = get_by_ticker("Rice, Thai 5% ", 'rice_thai5.csv', START, END)
rice.name = "rice_thai5"

combined = pd.concat(
    [jet_fuel, eur_usd, eur_gbp, rice, durum, wheat],
    axis=1,
    join="outer"
)
combined.index = pd.to_datetime(combined.index)
combined.index.name = "time"
combined = combined.loc[START:END]
combined["source"] = "FRED/WorldBank/Yahoo"

print(f"\nDataset combinado: {len(combined)} filas, {combined.shape[1]} columnas")
print(combined.tail(5).to_string())


# ── 7. Guardar CSV (backup local) ─────────────────────────────────────────────
combined.to_csv("data/market_data_combined.csv", sep=",", decimal=".")
print("\nBackup guardado en data/market_data_combined.csv")


# ── 8. Insertar en TimescaleDB ────────────────────────────────────────────────
print("\nInsertando en TimescaleDB...")
client.upsert(combined)


# ── 9. Verificar ──────────────────────────────────────────────────────────────
client.summary()