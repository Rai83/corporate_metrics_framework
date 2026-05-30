import pandas as pd
import os

from src.repository.fred_client import download_by_ticker
from src.repository.world_bank_client import get_by_ticker
from src.repository.yf_client import download_tickers

os.makedirs("data", exist_ok=True)


START = "2019-01-01"
END   = "2024-12-31"

# ── IAG — Factor 1: Jet Fuel (USD/galón, semanal) ─────────────────────────────
print("Descargando jet fuel...")
jet_fuel = download_by_ticker("WJFUELUSGULF", "jet_fuel_usd_gal", START, END)
jet_fuel = jet_fuel.resample("1MS").mean()
jet_fuel.to_csv("data/jet_fuel.csv", header=True)

# ── EBRO — Factor 1: Trigo duro (PPI index, mensual) ─────────────────────────
print("Descargando durum wheat...")
durum = download_by_ticker("WPU01210105", "durum_wheat_ppi", START, END)
durum.to_csv("data/durum_wheat.csv", header=True)

# ── EBRO — Factor 2: Precio global trigo (USD/tonelada métrica) ───────────────
print("Descargando global wheat price...")
wheat = download_by_ticker("PWHEAMTUSDM", "wheat_usd_mt", START, END)
wheat.to_csv("data/wheat_global.csv", header=True)

# ── FX: EUR/USD y EUR/GBP (diario → mensual) ─────────────────────────────────
print("Descargando FX rates...")
fx_tickers = {
    "EURUSD=X": "eur_usd",
    "EURGBP=X": "eur_gbp",
}
fx_frames = download_tickers(fx_tickers, START, END)
fx_frames.to_csv("data/fx_rates.csv")

rice_thai5 = get_by_ticker("Rice, Thai 5% ", 'rice_thai5.csv', START, END)

print("Construyendo dataset combinado...")
combined = pd.concat([jet_fuel, durum, wheat, fx_frames, rice_thai5], axis=1, sort=True)
combined.index.name = "date"
combined = combined.loc[START:END].dropna(how="all")
combined.to_csv("data/market_data_combined.csv")

print("\nArchivos generados:")
for f in os.listdir("data"):
    size = os.path.getsize(f"data/{f}")
    print(f"  data/{f}  ({size:,} bytes)")