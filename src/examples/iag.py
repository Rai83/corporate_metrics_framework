import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec
from src.db.client import MarketPricesClient

# ══════════════════════════════════════════════════════════════════════════════
# PARÁMETROS IAG 2024 — extraídos del informe anual
# Fuentes: IAG Full Year Results 2024, Q3 2024 Results
# ══════════════════════════════════════════════════════════════════════════════

IAG = {
    # Financials 2024
    "revenue_eur"       : 32_100,   # €mm — ingresos totales
    "operating_profit"  :  4_301,   # €mm — beneficio operativo
    "operating_margin"  :  0.134,   # 13.4%

    # Fuel — mayor coste operativo
    # Fuel cost ~€7,700mm (Q3 guidance), ~24% revenue
    "fuel_cost_eur"     :  7_700,   # €mm — coste total de fuel 2024
    "fuel_hedged_pct"   :  0.65,    # 65% hedgeado (rango 60-70%)
    "fuel_unhedged_pct" :  0.35,    # 35% exposición residual

    # FX — IAG genera déficit en USD (fuel + capex + deuda en USD)
    # GBP surplus: BA genera ingresos en GBP pero reporta en EUR
    "usd_net_deficit_eur":  2_500,  # €mm — déficit neto USD estimado
    "gbp_surplus_eur"    :  4_000,  # €mm — superávit neto GBP (BA revenues)
    "fx_hedged_pct"      :  0.60,   # 60% de exposición transaccional hedgeada

    # Sensibilidades (del informe anual)
    # $10/bbl cambio en jet fuel → impacto en operating profit
    "fuel_sensitivity_per_10usd_bbl" : 250,    # €mm por $10/bbl
    # 1 cent EUR/USD → impacto en operating profit
    "fx_usd_sensitivity_per_cent"    :  25,    # €mm por $0.01 EUR/USD
    # 1 cent EUR/GBP → impacto en operating profit
    "fx_gbp_sensitivity_per_cent"    :  40,    # €mm por £0.01 EUR/GBP
}

N_SCENARIOS = 10_000
N_QUARTERS  = 4
DT          = 0.25
SEED        = 42

# ══════════════════════════════════════════════════════════════════════════════
# 1. CARGAR DATOS HISTÓRICOS DE TIMESCALEDB
# ══════════════════════════════════════════════════════════════════════════════
print("Cargando datos de TimescaleDB...")
client = MarketPricesClient()

df = client.select(
    codes=["jet_fuel", "eur_usd", "eur_gbp"],
    start="2019-01-01",
    end="2024-12-31",
    pivot=True
).dropna()

print(f"Datos cargados: {len(df)} observaciones mensuales")
print(df.tail(3).to_string())

# ══════════════════════════════════════════════════════════════════════════════
# 2. RETORNOS LOGARÍTMICOS Y PARÁMETROS
# ══════════════════════════════════════════════════════════════════════════════
log_ret = np.log(df / df.shift(1)).dropna()

# Parámetros anualizados por serie
params = {}
for col in log_ret.columns:
    mu    = log_ret[col].mean() * 12           # drift anual
    sigma = log_ret[col].std()  * np.sqrt(12)  # volatilidad anual
    params[col] = {"mu": mu, "sigma": sigma}
    print(f"  {col:<12} μ={mu:+.2%}  σ={sigma:.2%}")

# Matriz de correlación (mensual → usada en Cholesky)
corr_matrix = log_ret.corr()
print("\nMatriz de correlación:")
print(corr_matrix.round(3).to_string())

# ══════════════════════════════════════════════════════════════════════════════
# 3. SIMULACIÓN MONTE CARLO CORRELACIONADA (Cholesky)
# ══════════════════════════════════════════════════════════════════════════════
rng  = np.random.default_rng(SEED)
cols = list(params.keys())   # ['jet_fuel', 'eur_usd', 'eur_gbp']

# Descomposición de Cholesky para correlacionar los shocks
cov_monthly = log_ret.cov().values
L = np.linalg.cholesky(cov_monthly)

# Spot values (último dato disponible)
spots = {col: df[col].iloc[-1] for col in cols}
print(f"\nSpot values (dic 2024):")
for k, v in spots.items():
    print(f"  {k:<12}: {v:.4f}")

# Generar paths: shape (N_SCENARIOS, N_QUARTERS+1, N_FACTORS)
paths = {col: np.zeros((N_SCENARIOS, N_QUARTERS + 1)) for col in cols}
for col in cols:
    paths[col][:, 0] = spots[col]

for t in range(N_QUARTERS):
    # Shocks independientes
    Z_ind = rng.standard_normal((N_SCENARIOS, len(cols)))
    # Shocks correlacionados via Cholesky
    Z_cor = Z_ind @ L.T

    for i, col in enumerate(cols):
        mu_q    = params[col]["mu"]    * DT
        sigma_q = params[col]["sigma"] * np.sqrt(DT)
        drift   = (mu_q - 0.5 * sigma_q**2)
        paths[col][:, t + 1] = (
            paths[col][:, t] *
            np.exp(drift + sigma_q * Z_cor[:, i])
        )

# ══════════════════════════════════════════════════════════════════════════════
# 4. MAPEAR ESCENARIOS → IMPACTO EN OPERATING PROFIT
# ══════════════════════════════════════════════════════════════════════════════
def quarterly_op_profit(jet_q, eurusd_q, eurgbp_q):
    """
    Calcula el impacto en operating profit para un escenario de precios.

    Lógica:
    - Fuel: coste trimestral no hedgeado × (precio_simulado / precio_spot - 1)
    - USD FX: déficit USD × (1/eurusd_simulado - 1/eurusd_spot) × spot_adjustment
    - GBP FX: superávit GBP × (1/eurgbp_simulado - 1/eurgbp_spot) × spot_adjustment
    """
    fuel_unhedged_q = IAG["fuel_cost_eur"] * IAG["fuel_unhedged_pct"] / 4

    # Impacto fuel: cambio porcentual en precio × coste no hedgeado
    fuel_change = jet_q / spots["jet_fuel"] - 1.0
    fuel_impact = -fuel_unhedged_q * fuel_change       # sube fuel → baja profit

    # Impacto FX USD: IAG tiene déficit en USD
    # Si EUR/USD sube (EUR se aprecia) → déficit USD es más barato en EUR → positivo
    usd_unhedged_q = IAG["usd_net_deficit_eur"] * (1 - IAG["fx_hedged_pct"]) / 4
    usd_change     = eurusd_q / spots["eur_usd"] - 1.0
    usd_impact     = usd_unhedged_q * usd_change        # EUR aprecia → positivo

    # Impacto FX GBP: IAG tiene superávit en GBP (ingresos BA)
    # Si EUR/GBP sube (EUR se aprecia vs GBP) → ingresos GBP valen menos → negativo
    gbp_unhedged_q = IAG["gbp_surplus_eur"] * (1 - IAG["fx_hedged_pct"]) / 4
    gbp_change     = eurgbp_q / spots["eur_gbp"] - 1.0
    gbp_impact     = -gbp_unhedged_q * gbp_change       # EUR aprecia → negativo

    return fuel_impact + usd_impact + gbp_impact


# Operating profit base trimestral
op_profit_base_q = IAG["operating_profit"] / 4

# Calcular operating profit anual para cada escenario
annual_op_profit = np.zeros(N_SCENARIOS)

for t in range(1, N_QUARTERS + 1):
    jet_q    = paths["jet_fuel"][:, t]
    eurusd_q = paths["eur_usd"][:, t]
    eurgbp_q = paths["eur_gbp"][:, t]

    impact_q = quarterly_op_profit(jet_q, eurusd_q, eurgbp_q)
    annual_op_profit += op_profit_base_q + impact_q

# ══════════════════════════════════════════════════════════════════════════════
# 5. EAR — Earnings at Risk
# ══════════════════════════════════════════════════════════════════════════════
mean_profit = np.mean(annual_op_profit)
pct5        = np.percentile(annual_op_profit, 5)
pct25       = np.percentile(annual_op_profit, 25)
pct75       = np.percentile(annual_op_profit, 75)
pct95       = np.percentile(annual_op_profit, 95)
ear_95      = mean_profit - pct5
std_profit  = np.std(annual_op_profit)

print(f"\n{'='*50}")
print(f"  IAG — Earnings at Risk (datos reales 2024)")
print(f"{'='*50}")
print(f"  Operating profit esperado : €{mean_profit:>8,.0f}mm")
print(f"  Base (informe anual)      : €{IAG['operating_profit']:>8,.0f}mm")
print(f"  Desv. estándar            : €{std_profit:>8,.0f}mm")
print(f"  Percentil  5              : €{pct5:>8,.0f}mm")
print(f"  Percentil 95              : €{pct95:>8,.0f}mm")
print(f"  EaR (95%)                 : €{ear_95:>8,.0f}mm")
print(f"  EaR / Operating profit    :  {ear_95/mean_profit:>8.1%}")

# ══════════════════════════════════════════════════════════════════════════════
# 6. PLOTS
# ══════════════════════════════════════════════════════════════════════════════
fig = plt.figure(figsize=(16, 12))
fig.patch.set_facecolor("#FAFAFA")
gs  = gridspec.GridSpec(2, 2, figure=fig, hspace=0.40, wspace=0.35)

quarters  = ["Dic 2024\n(spot)", "Mar 2025\nQ1", "Jun 2025\nQ2",
             "Sep 2025\nQ3", "Dic 2025\nQ4"]
BLUE      = "#185FA5"
RED       = "#A32D2D"
AMBER     = "#E2763A"
GREEN     = "#3B6D11"

# ── Plot 1: Distribución de Operating Profit (EaR) ───────────────────────────
ax1 = fig.add_subplot(gs[0, :])
ax1.set_facecolor("#FAFAFA")

n_counts, bins, patches_list = ax1.hist(
    annual_op_profit, bins=100,
    color="#B5D4F4", edgecolor="white", linewidth=0.3,
    density=True, zorder=2
)
for patch, left in zip(patches_list, bins[:-1]):
    if left < pct5:
        patch.set_facecolor("#F09595")
    elif left < pct25:
        patch.set_facecolor("#FAC775")

ax1.axvspan(annual_op_profit.min(), pct5,
            alpha=0.08, color="#E24B4A", zorder=1)

ax1.axvline(mean_profit, color=BLUE,  linewidth=2.0, linestyle="-",
            label=f"Media: €{mean_profit:,.0f}mm")
ax1.axvline(pct5,        color=RED,   linewidth=1.8, linestyle="--",
            label=f"Pct 5: €{pct5:,.0f}mm")
ax1.axvline(pct95,       color=AMBER, linewidth=1.4, linestyle="--",
            label=f"Pct 95: €{pct95:,.0f}mm")
ax1.axvline(IAG["operating_profit"], color=GREEN, linewidth=1.6,
            linestyle=":", label=f"Target 2024: €{IAG['operating_profit']:,}mm")

y_top    = n_counts.max()
y_arrow  = y_top * 0.78
ax1.annotate("", xy=(pct5, y_arrow), xytext=(mean_profit, y_arrow),
             arrowprops=dict(arrowstyle="<->", color=RED, lw=1.6))
ax1.text((pct5 + mean_profit) / 2, y_arrow * 1.032,
         f"EaR (95%) = €{ear_95:,.0f}mm",
         ha="center", va="bottom", fontsize=10,
         color=RED, fontweight="bold")

ax1.set_title("IAG — Distribución de Operating Profit anual\n"
              "Monte Carlo 10,000 escenarios · datos reales 2019–2024 · horizonte 4 trimestres",
              fontsize=11, color="#2C2C2A", loc="left", pad=10)
ax1.set_xlabel("Operating profit anual (€mm)", fontsize=10, color="#555")
ax1.set_ylabel("Densidad de probabilidad",     fontsize=10, color="#555")
ax1.xaxis.set_major_formatter(
    plt.FuncFormatter(lambda x, _: f"€{x:,.0f}mm"))
ax1.tick_params(colors="#666", labelsize=9)
ax1.spines[["top", "right"]].set_visible(False)
ax1.spines[["left", "bottom"]].set_color("#D3D1C7")
ax1.grid(axis="x", color="#D3D1C7", linewidth=0.5, linestyle="--", zorder=0)
ax1.legend(fontsize=9, framealpha=0.6, loc="upper left")

# ── Plot 2: Banda JPY-style para Jet Fuel ─────────────────────────────────────
ax2 = fig.add_subplot(gs[1, 0])
ax2.set_facecolor("#FAFAFA")

fuel_mean = [np.mean(paths["jet_fuel"][:, t]) for t in range(N_QUARTERS + 1)]
fuel_p5   = [np.percentile(paths["jet_fuel"][:, t], 5)  for t in range(N_QUARTERS + 1)]
fuel_p95  = [np.percentile(paths["jet_fuel"][:, t], 95) for t in range(N_QUARTERS + 1)]

ax2.fill_between(range(N_QUARTERS + 1), fuel_p5, fuel_p95,
                 alpha=0.15, color=BLUE, label="Banda 5%–95%")
ax2.plot(fuel_mean, color=BLUE,  linewidth=2.0,
         marker="o", markersize=4, label="Media")
ax2.plot(fuel_p5,   color=BLUE,  linewidth=0.8,
         linestyle="--", marker="s", markersize=3)
ax2.plot(fuel_p95,  color=BLUE,  linewidth=0.8,
         linestyle="--", marker="s", markersize=3)

ax2.set_xticks(range(N_QUARTERS + 1))
ax2.set_xticklabels(quarters, fontsize=8)
ax2.set_title("Jet Fuel — distribución de escenarios\n(USD/galón)",
              fontsize=10, color="#2C2C2A", loc="left", pad=8)
ax2.set_ylabel("USD/galón", fontsize=9, color="#555")
ax2.tick_params(colors="#666", labelsize=9)
ax2.spines[["top", "right"]].set_visible(False)
ax2.spines[["left", "bottom"]].set_color("#D3D1C7")
ax2.grid(color="#D3D1C7", linewidth=0.5, linestyle="--", zorder=0)
ax2.legend(fontsize=8, framealpha=0.6)

# ── Plot 3: Banda EUR/USD ──────────────────────────────────────────────────────
ax3 = fig.add_subplot(gs[1, 1])
ax3.set_facecolor("#FAFAFA")

usd_mean = [np.mean(paths["eur_usd"][:, t]) for t in range(N_QUARTERS + 1)]
usd_p5   = [np.percentile(paths["eur_usd"][:, t], 5)  for t in range(N_QUARTERS + 1)]
usd_p95  = [np.percentile(paths["eur_usd"][:, t], 95) for t in range(N_QUARTERS + 1)]

ax3.fill_between(range(N_QUARTERS + 1), usd_p5, usd_p95,
                 alpha=0.15, color=AMBER, label="Banda 5%–95%")
ax3.plot(usd_mean, color=AMBER, linewidth=2.0,
         marker="o", markersize=4, label="Media")
ax3.plot(usd_p5,   color=AMBER, linewidth=0.8,
         linestyle="--", marker="s", markersize=3)
ax3.plot(usd_p95,  color=AMBER, linewidth=0.8,
         linestyle="--", marker="s", markersize=3)

ax3.set_xticks(range(N_QUARTERS + 1))
ax3.set_xticklabels(quarters, fontsize=8)
ax3.set_title("EUR/USD — distribución de escenarios",
              fontsize=10, color="#2C2C2A", loc="left", pad=8)
ax3.set_ylabel("EUR/USD", fontsize=9, color="#555")
ax3.tick_params(colors="#666", labelsize=9)
ax3.spines[["top", "right"]].set_visible(False)
ax3.spines[["left", "bottom"]].set_color("#D3D1C7")
ax3.grid(color="#D3D1C7", linewidth=0.5, linestyle="--", zorder=0)
ax3.legend(fontsize=8, framealpha=0.6)

fig.suptitle(
    "IAG — Earnings at Risk (EaR) · CorporateMetrics framework\n"
    "Datos reales 2019–2024 · Horizonte 4 trimestres 2025",
    fontsize=12, color="#2C2C2A", y=1.01
)

import os
os.makedirs("output", exist_ok=True)
plt.savefig("output/iag_ear_2024.png",
            dpi=150, bbox_inches="tight", facecolor="#FAFAFA")
plt.show()
print("Guardado: output/iag_ear_2024.png")