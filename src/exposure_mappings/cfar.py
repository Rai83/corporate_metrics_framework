"""
cfar.py
═══════════════════════════════════════════════════════════════════════════
Motor de cálculo del Cash Flow at Risk (v3 — P&L decomposition).

Formulación:
  Operating CF = Revenue - Operating Costs - Taxes - ΔWC
  Cada exposición se mapea a una línea de la P&L.
  Los impuestos se recalculan automáticamente sobre EBITDA simulado.

Uso:
  python -m src.cfar config/exposure_maps/iag_2026.yaml   (desde la raíz)
"""
import os
import sys

import matplotlib.gridspec as gridspec
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from src.db.client import MarketPricesClient
from src.exposure_mappings.exposure_functions import apply_exposure_quarter
from src.exposure_mappings.exposure_map import ExposureMap, VALID_PL_LINES



def load_historical_data(factor_codes: list, start: str, end: str) -> pd.DataFrame:
    client = MarketPricesClient()
    df = client.select(codes=factor_codes, start=start, end=end, pivot=True)
    return df.dropna()


def simulate_scenarios(df_historical: pd.DataFrame,
                       n_scenarios:   int,
                       n_quarters:    int,
                       seed:          int = 42) -> tuple:
    log_ret    = np.log(df_historical / df_historical.shift(1)).dropna()
    cols       = list(log_ret.columns)
    spots      = {col: df_historical[col].iloc[-1] for col in cols}

    mu_monthly  = log_ret.mean().values
    cov_monthly = log_ret.cov().values
    L           = np.linalg.cholesky(cov_monthly)

    rng = np.random.default_rng(seed)
    paths = {col: np.zeros((n_scenarios, n_quarters + 1)) for col in cols}
    for col in cols:
        paths[col][:, 0] = spots[col]

    months_per_quarter = 3
    for t in range(n_quarters):
        Z_q = rng.standard_normal((n_scenarios, len(cols))) @ L.T \
              * np.sqrt(months_per_quarter)
        for i, col in enumerate(cols):
            drift_q = (mu_monthly[i] * months_per_quarter
                       - 0.5 * cov_monthly[i, i] * months_per_quarter)
            paths[col][:, t + 1] = paths[col][:, t] * np.exp(drift_q + Z_q[:, i])

    return paths, spots, log_ret


def calculate_pl_impacts(em: ExposureMap, paths: dict, spots: dict) -> dict:
    """
    Calcula el impacto agregado sobre cada línea de la P&L y por factor.

    Devuelve dict con estructura:
      impacts['by_line'][pl_line]      → array (n_scenarios,) impacto agregado
      impacts['by_factor'][factor][t]  → array (n_scenarios,) por trimestre
      impacts['by_factor'][factor]['_annual'] → suma anual por factor
    """
    n_quarters  = em.horizon_quarters
    n_scenarios = em.simulation_config["n_scenarios"]

    by_line   = {line: np.zeros(n_scenarios) for line in VALID_PL_LINES}
    by_factor = {}

    for exp in em.exposures:
        factor_paths = paths[exp.factor_code]
        spot         = spots[exp.factor_code]
        quantity     = exp.parameters["quantity"]
        distribution = exp.parameters.get(
            "quarterly_distribution",
            [1.0 / n_quarters] * n_quarters
        )

        # Configuración de conversión FX (opcional)
        currency_conv = exp.parameters.get("currency_conversion")
        if currency_conv:
            conv_paths = paths[currency_conv["factor_code"]]
            conv_type  = currency_conv.get("type", "divide")
        else:
            conv_paths = None
            conv_type  = None

        by_factor[exp.factor_code] = {}
        annual = np.zeros(n_scenarios)

        for t in range(n_quarters):
            quantity_q = quantity * distribution[t]
            factor_q   = factor_paths[:, t + 1]

            impact_raw = apply_exposure_quarter(factor_q, spot, quantity_q, exp)

            if conv_paths is not None:
                conv_q = conv_paths[:, t + 1]
                impact_q = (impact_raw / conv_q if conv_type == "divide"
                            else impact_raw * conv_q)
            else:
                impact_q = impact_raw

            by_factor[exp.factor_code][t] = impact_q
            annual += impact_q

        by_factor[exp.factor_code]["_annual"] = annual
        by_line[exp.pl_line] += annual

    return {"by_line": by_line, "by_factor": by_factor}


def calculate_hedge_costs(em: ExposureMap, spots: dict) -> dict:
    """
    Calcula el coste anual de cobertura por exposición y lo asigna a la
    línea P&L correspondiente (la misma que la exposición que cubre).

    Devuelve dict con:
      costs[factor_code]    : coste anual de esa cobertura
      costs['by_line'][line]: coste agregado por línea P&L
      costs['_total']       : suma total
    """
    costs = {"_total": 0.0,
             "by_line": {line: 0.0 for line in VALID_PL_LINES}}

    for exp in em.exposures:
        bps = exp.parameters.get("hedge_cost_bps", 0)
        if bps == 0:
            costs[exp.factor_code] = 0.0
            continue

        quantity     = exp.parameters["quantity"]
        hedge_ratio  = exp.parameters["hedge_ratio"]
        spot         = spots[exp.factor_code]
        inverse_rate = exp.parameters.get("inverse_rate", False)

        if inverse_rate:
            value_functional = quantity / spot
        else:
            value_in_price = quantity * spot
            conv = exp.parameters.get("currency_conversion")
            if conv:
                conv_spot = spots[conv["factor_code"]]
                value_functional = (value_in_price / conv_spot
                                    if conv["type"] == "divide"
                                    else value_in_price * conv_spot)
            else:
                value_functional = value_in_price

        cost = value_functional * hedge_ratio * (bps / 10000.0)
        costs[exp.factor_code] = cost
        costs["by_line"][exp.pl_line] += cost
        costs["_total"] += cost
    return costs


def build_target_with_hedge_only(em: ExposureMap, hedge_costs: dict) -> dict:
    """
    Propaga el coste de cobertura por la cadena P&L para obtener un
    'target neto' — el valor que tendría cada línea financiera si no
    hubiera movimientos de mercado pero sí se pagase la prima de cobertura.

    Esta función es necesaria para la postura B (Markowitz auténtico) del
    cálculo del CFaR: el target con el que se compara el percentil 5 debe
    estar en la misma escala que la distribución simulada (que ya incluye
    el coste de cobertura).

    El cálculo replica build_simulated_cash_flow con pl_impacts = 0,
    de modo que solo el coste de cobertura se propaga por la cadena.
    Esto captura automáticamente el escudo fiscal sobre el propio coste:
    el coste reduce el EBIT, los impuestos disminuyen proporcionalmente,
    y el impacto neto sobre el cash flow es coste × (1 - tax_rate).

    Devuelve un dict con las mismas claves que cash_flow_target, pero
    con los valores netos del coste de cobertura.
    """
    cf  = em.cash_flow_target
    hbl = hedge_costs["by_line"]

    revenue_neto         = cf.revenue          - hbl["revenue"]
    operating_costs_neto = cf.operating_costs  + hbl["operating_costs"]
    wc_change_neto       = cf.wc_change        # WC no afectado por hedge

    ebitda_neto = revenue_neto - operating_costs_neto
    ebit_neto   = ebitda_neto - cf.depreciation_amortization

    # Impuestos recalculados sobre el EBIT neto + coste fiscal del hedge
    taxes_neto = ebit_neto * em.tax_rate + hbl["taxes"]
    nopat_neto = ebit_neto - taxes_neto

    # Operating CF: devolver D&A no-cash y sumar WC change
    opcf_neto = nopat_neto + cf.depreciation_amortization + wc_change_neto

    return {
        "revenue":         revenue_neto,
        "operating_costs": operating_costs_neto,
        "ebitda":          ebitda_neto,
        "ebit":            ebit_neto,
        "taxes":           taxes_neto,
        "nopat":           nopat_neto,
        "wc_change":       wc_change_neto,
        "operating_cf":    opcf_neto,
    }


def build_simulated_cash_flow(em: ExposureMap, pl_impacts: dict,
                              hedge_costs: dict) -> dict:
    """
    Construye el Operating CF simulado a partir de los impactos por línea P&L.

    Cadena de cálculo:
      Revenue          = revenue_target          + impactos_revenue   - hedge_costs.revenue
      Operating costs  = operating_costs_target  + impactos_costs     + hedge_costs.operating_costs
      EBITDA           = Revenue - Operating costs
      D&A              = D&A_target  (no expuesto al riesgo de mercado)
      EBIT             = EBITDA - D&A
      Taxes            = EBIT × tax_rate         + impactos_taxes     + hedge_costs.taxes
      NOPAT            = EBIT - Taxes
      Operating CF     = NOPAT + D&A + WC change
                       (la D&A se devuelve por ser concepto no-cash)

    Esta formulación captura correctamente el escudo fiscal de la D&A:
    al reducir el EBIT, reduce los impuestos pagados, lo que se traduce
    en mayor cash flow.
    """
    cf  = em.cash_flow_target
    hbl = hedge_costs["by_line"]

    revenue_sim = (cf.revenue
                   + pl_impacts["by_line"]["revenue"]
                   - hbl["revenue"])
    operating_costs_sim = (cf.operating_costs
                           + pl_impacts["by_line"]["operating_costs"]
                           + hbl["operating_costs"])
    wc_change_sim = (cf.wc_change
                     + pl_impacts["by_line"]["wc_change"])

    ebitda_sim = revenue_sim - operating_costs_sim
    ebit_sim   = ebitda_sim - cf.depreciation_amortization

    # Impuestos: recalculados sobre EBIT simulado (no sobre EBITDA)
    # La D&A actúa como escudo fiscal porque reduce la base imponible
    taxes_sim = (ebit_sim * em.tax_rate
                 + pl_impacts["by_line"]["taxes"]
                 + hbl["taxes"])

    nopat_sim = ebit_sim - taxes_sim

    # Operating CF: devolver la D&A (no-cash) y sumar variación de WC
    operating_cf_sim = nopat_sim + cf.depreciation_amortization + wc_change_sim

    return {
        "revenue":         revenue_sim,
        "operating_costs": operating_costs_sim,
        "ebitda":          ebitda_sim,
        "ebit":            ebit_sim,
        "taxes":           taxes_sim,
        "nopat":           nopat_sim,
        "wc_change":       wc_change_sim,
        "operating_cf":    operating_cf_sim,
    }


def compute_at_risk(values: np.ndarray, target: float,
                    confidence: float = 0.95) -> dict:
    """
    Calcula la métrica at-risk respecto al target.

    Definición CorporateMetrics:
        at_risk = target - cuantil(1-α)

    Postura metodológica adoptada (B, Markowitz auténtico):
    El `target` que se pasa a esta función debe estar NETO del coste de
    cobertura — es decir, debe ser el resultado de propagar las primas
    de cobertura por la cadena P&L (ver build_target_with_hedge_only).
    De esta forma, tanto el target como el percentil de la distribución
    simulada están en la misma escala, y el at_risk mide exclusivamente
    el riesgo residual atribuible a los movimientos de mercado.

    El drift histórico de los factores y el efecto fiscal sí quedan
    incluidos en el at_risk medido, ya que constituyen sesgos sistemáticos
    inherentes al modelo y no decisiones discrecionales como las coberturas.
    """
    pct_lower = (1 - confidence) * 100
    pct_5     = float(np.percentile(values, pct_lower))

    return {
        "values":     values,
        "target":     target,
        "mean":       float(np.mean(values)),
        "std":        float(np.std(values)),
        "pct_5":      pct_5,
        "median":     float(np.percentile(values, 50)),
        "pct_95":     float(np.percentile(values, 100 - pct_lower)),
        "at_risk":    target - pct_5,
        "confidence": confidence,
    }


def plot_cfar(em: ExposureMap, paths: dict, sim: dict, cfar: dict,
              output_dir: str = "output"):
    BLUE, RED, AMBER, GREEN = "#185FA5", "#A32D2D", "#E2763A", "#3B6D11"

    n_quarters = em.horizon_quarters
    quarters   = ["Spot"] + [f"Q{i+1}" for i in range(n_quarters)]
    n_factors  = len(em.exposures)

    fig = plt.figure(figsize=(16, 5 + 3 * ((n_factors + 1) // 2)))
    fig.patch.set_facecolor("#FAFAFA")
    n_rows = 1 + (n_factors + 1) // 2
    gs = gridspec.GridSpec(n_rows, 2, figure=fig, hspace=0.55, wspace=0.30,
                           top=0.93, bottom=0.06, left=0.07, right=0.97)

    ax1 = fig.add_subplot(gs[0, :])
    ax1.set_facecolor("#FAFAFA")
    cf       = sim["operating_cf"]
    pct5     = cfar["pct_5"]
    pct95    = cfar["pct_95"]
    mean_cf  = cfar["mean"]
    target   = cfar["target"]
    at_risk  = cfar["at_risk"]

    n_counts, bins, patches = ax1.hist(
        cf, bins=100, color="#B5D4F4", edgecolor="white",
        linewidth=0.3, density=True, zorder=2
    )
    for patch, left in zip(patches, bins[:-1]):
        if left < pct5:
            patch.set_facecolor("#F09595")

    ax1.axvspan(cf.min(), pct5, alpha=0.08, color="#E24B4A", zorder=1)
    ax1.axvline(mean_cf, color=BLUE,  linewidth=2.0,
                label=f"Media: €{mean_cf:,.0f} mm")
    ax1.axvline(pct5,    color=RED,   linewidth=1.8, linestyle="--",
                label=f"Pct 5: €{pct5:,.0f} mm")
    ax1.axvline(pct95,   color=AMBER, linewidth=1.4, linestyle="--",
                label=f"Pct 95: €{pct95:,.0f} mm")
    ax1.axvline(target,  color=GREEN, linewidth=1.6, linestyle=":",
                label=f"Target: €{target:,.0f} mm")

    y_top   = n_counts.max()
    y_arrow = y_top * 0.78
    ax1.annotate("", xy=(pct5, y_arrow), xytext=(target, y_arrow),
                 arrowprops=dict(arrowstyle="<->", color=RED, lw=1.6))
    ax1.text((pct5 + target) / 2, y_arrow * 1.04,
             f"CFaR (95%) = €{at_risk:,.0f} mm",
             ha="center", va="bottom", fontsize=10,
             color=RED, fontweight="bold")

    ax1.set_title(f"{em.company_name} — Operating CF {em.reporting_period}\n"
                  f"P&L decomposition · {len(cf):,} escenarios",
                  fontsize=11, color="#2C2C2A", loc="left", pad=10)
    ax1.set_xlabel(f"Operating Cash Flow ({em.functional_currency} mm)",
                   fontsize=10, color="#555")
    ax1.set_ylabel("Densidad", fontsize=10, color="#555")
    ax1.xaxis.set_major_formatter(plt.FuncFormatter(lambda x, _: f"€{x:,.0f}"))
    ax1.tick_params(colors="#666", labelsize=9)
    ax1.spines[["top", "right"]].set_visible(False)
    ax1.spines[["left", "bottom"]].set_color("#D3D1C7")
    ax1.grid(axis="x", color="#D3D1C7", linewidth=0.5, linestyle="--", zorder=0)
    ax1.legend(fontsize=9, framealpha=0.6, loc="upper left")

    factor_colors = [BLUE, AMBER, GREEN, RED, "#7B5BA0"]
    for idx, exp in enumerate(em.exposures):
        row = 1 + idx // 2
        col = idx % 2
        ax = fig.add_subplot(gs[row, col])
        ax.set_facecolor("#FAFAFA")
        color = factor_colors[idx % len(factor_colors)]

        path_arr = paths[exp.factor_code]
        mean_p = [np.mean(path_arr[:, t])         for t in range(n_quarters + 1)]
        p5_p   = [np.percentile(path_arr[:, t], 5)  for t in range(n_quarters + 1)]
        p95_p  = [np.percentile(path_arr[:, t], 95) for t in range(n_quarters + 1)]

        ax.fill_between(range(n_quarters + 1), p5_p, p95_p,
                        alpha=0.15, color=color, label="5%–95%")
        ax.plot(mean_p, color=color, linewidth=2.0, marker="o",
                markersize=4, label="Media")
        ax.plot(p5_p,  color=color, linewidth=0.8, linestyle="--")
        ax.plot(p95_p, color=color, linewidth=0.8, linestyle="--")

        ax.set_xticks(range(n_quarters + 1))
        ax.set_xticklabels(quarters, fontsize=8)
        ax.set_title(f"{exp.factor_name} → {exp.pl_line}",
                     fontsize=10, color="#2C2C2A", loc="left", pad=8)
        ax.tick_params(colors="#666", labelsize=9)
        ax.spines[["top", "right"]].set_visible(False)
        ax.spines[["left", "bottom"]].set_color("#D3D1C7")
        ax.grid(color="#D3D1C7", linewidth=0.5, linestyle="--", zorder=0)
        ax.legend(fontsize=8, framealpha=0.6)

    fig.suptitle(
        f"{em.company_name} — Cash Flow at Risk · CorporateMetrics framework",
        fontsize=12, color="#2C2C2A", y=0.985
    )

    out_path = f"{output_dir}/{em.company_code.lower()}_cfar_{em.reporting_period}.png"
    os.makedirs(output_dir, exist_ok=True)
    plt.savefig(out_path, dpi=150, bbox_inches="tight", facecolor="#FAFAFA")
    plt.show()
    return out_path


def _append_to_csv(df_new: pd.DataFrame, csv_path: str,
                   company_id: str, year: int) -> None:
    """
    Escribe un DataFrame a un CSV, manteniendo los datos de OTRAS empresas-año.
    Si el CSV ya existía con una entrada para esta empresa-año, la sustituye.
    """
    if os.path.exists(csv_path):
        df_old = pd.read_csv(csv_path)
        # Filtrar fuera la entrada anterior de esta empresa-año
        if "year" in df_old.columns:
            mask = ~((df_old["company_id"] == company_id) &
                     (df_old["year"] == year))
        else:
            mask = df_old["company_id"] != company_id
        df_old = df_old[mask]
        df_combined = pd.concat([df_old, df_new], ignore_index=True)
    else:
        df_combined = df_new

    df_combined.to_csv(csv_path, index=False, sep=",", decimal=".")


def export_results(em: ExposureMap, paths: dict, spots: dict, sim: dict,
                   pl_impacts: dict, hedge_costs: dict, results: dict,
                   target_neto: dict, output_dir: str = "output"):
    """
    Exports 6 CSVs in start modelfor Power BI:
      1. companies.csv          — Companies dimension
      2. cfar_summary.csv       — KPIs per company-year
      3. cfar_scenarios.csv     — 10.000 yearly scenarios per company
      4. cfar_decomposition.csv — factor decomposition + quarter
      5. factor_quantiles.csv   — quarter percentiles
      6. highlight_scenarios.csv — top 5 and bottom 5 scenarios
    """
    os.makedirs(output_dir, exist_ok=True)
    company_id  = em.company_code
    company_name= em.company_name
    year        = em.reporting_period
    n_quarters  = em.horizon_quarters
    n_scenarios = len(sim["operating_cf"])

    # ──────────────────────────────────────────────────────────────────────
    # 1. companies.csv
    # ──────────────────────────────────────────────────────────────────────
    df_companies = pd.DataFrame([{
        "company_id":   company_id,
        "company_name": company_name,
        "currency":     em.functional_currency,
        "tax_rate":     em.tax_rate,
        "horizon_q":    n_quarters,
        "n_scenarios":  n_scenarios,
        "data_window":  f"{em.simulation_config['historical_data_window']['start']}"
                        f" → {em.simulation_config['historical_data_window']['end']}",
    }])
    _append_to_csv(df_companies,
                   f"{output_dir}/companies.csv",
                   company_id, year=None)

    # ──────────────────────────────────────────────────────────────────────
    # 2. cfar_summary.csv — KPIs
    # ──────────────────────────────────────────────────────────────────────
    cf       = em.cash_flow_target
    pct5     = results["pct_5"]
    pct95    = results["pct_95"]
    target   = cf.operating_cf

    df_summary = pd.DataFrame([{
        "company_id":         company_id,
        "year":               year,
        "currency":           em.functional_currency,
        "revenue_target":     cf.revenue,
        "opex_target":        cf.operating_costs,
        "ebitda_target":      cf.ebitda,
        "da_target":          cf.depreciation_amortization,
        "ebit_target":        cf.ebit,
        "taxes_target":       cf.taxes,
        "nopat_target":       cf.nopat,
        "wc_change_target":   cf.wc_change,
        "opcf_target":        target,
        "revenue_target_neto":    target_neto["revenue"],
        "opex_target_neto":       target_neto["operating_costs"],
        "ebitda_target_neto":     target_neto["ebitda"],
        "ebit_target_neto":       target_neto["ebit"],
        "taxes_target_neto":      target_neto["taxes"],
        "nopat_target_neto":      target_neto["nopat"],
        "opcf_target_neto":       target_neto["operating_cf"],
        "opcf_mean":          results["mean"],
        "opcf_std":           results["std"],
        "opcf_pct5":          pct5,
        "opcf_pct95":         pct95,
        "cfar_95":            target_neto["operating_cf"] - pct5,
        "cfar_pct_target":    (target_neto["operating_cf"] - pct5) / target_neto["operating_cf"],
        "hedge_cost_total":   hedge_costs["_total"],
    }])
    _append_to_csv(df_summary,
                   f"{output_dir}/cfar_summary.csv",
                   company_id, year)

    df_scen = pd.DataFrame({"scenario_id": np.arange(n_scenarios)})
    df_scen["company_id"] = company_id
    df_scen["year"]       = year
    for line in ["revenue", "operating_costs", "ebitda", "ebit",
                 "taxes", "nopat", "wc_change", "operating_cf"]:
        df_scen[line] = sim[line]
    for code in em.factor_codes():
        df_scen[f"impact_{code}"] = pl_impacts["by_factor"][code]["_annual"]
    _append_to_csv(df_scen,
                   f"{output_dir}/cfar_scenarios.csv",
                   company_id, year)


    rows = []
    for exp in em.exposures:
        for t in range(n_quarters):
            arr = pl_impacts["by_factor"][exp.factor_code][t]
            rows.append({
                "company_id":   company_id,
                "year":         year,
                "factor_code":  exp.factor_code,
                "factor_name":  exp.factor_name,
                "pl_line":      exp.pl_line,
                "period":       f"Q{t+1}",
                "period_order": t + 1,
                "mean":         float(np.mean(arr)),
                "std":          float(np.std(arr)),
                "pct5":         float(np.percentile(arr, 5)),
                "pct95":        float(np.percentile(arr, 95)),
            })
        ann = pl_impacts["by_factor"][exp.factor_code]["_annual"]
        rows.append({
            "company_id":   company_id,
            "year":         year,
            "factor_code":  exp.factor_code,
            "factor_name":  exp.factor_name,
            "pl_line":      exp.pl_line,
            "period":       "Anual",
            "period_order": 5,
            "mean":         float(np.mean(ann)),
            "std":          float(np.std(ann)),
            "pct5":         float(np.percentile(ann, 5)),
            "pct95":        float(np.percentile(ann, 95)),
        })
    df_decomp = pd.DataFrame(rows)
    _append_to_csv(df_decomp,
                   f"{output_dir}/cfar_decomposition.csv",
                   company_id, year)

    quantile_rows = []
    for code in em.factor_codes():
        path_arr = paths[code]
        spot     = spots[code]
        for t in range(n_quarters + 1):
            values = path_arr[:, t]
            quantile_rows.append({
                "company_id":  company_id,
                "year":        year,
                "factor_code": code,
                "period":      "Spot" if t == 0 else f"Q{t}",
                "period_order":t,
                "p5":          float(np.percentile(values, 5)),
                "p25":         float(np.percentile(values, 25)),
                "mean":        float(np.mean(values)),
                "p75":         float(np.percentile(values, 75)),
                "p95":         float(np.percentile(values, 95)),
            })
    df_quantiles = pd.DataFrame(quantile_rows)
    _append_to_csv(df_quantiles,
                   f"{output_dir}/factor_quantiles.csv",
                   company_id, year)

    cf_sim     = sim["operating_cf"]
    sorted_idx = np.argsort(cf_sim)
    worst_5    = sorted_idx[:5]
    best_5     = sorted_idx[-5:][::-1]

    highlight_rows = []
    for rank, scen_idx in enumerate(worst_5, start=1):
        for code in em.factor_codes():
            for t in range(n_quarters + 1):
                highlight_rows.append({
                    "company_id":      company_id,
                    "year":            year,
                    "scenario_id":     int(scen_idx),
                    "rank_type":       f"worst_{rank}",
                    "rank_category":   "worst",
                    "rank_order":      rank,
                    "factor_code":     code,
                    "period":          "Spot" if t == 0 else f"Q{t}",
                    "period_order":    t,
                    "value":           float(paths[code][scen_idx, t]),
                    "scenario_opcf":   float(cf_sim[scen_idx]),
                })
    for rank, scen_idx in enumerate(best_5, start=1):
        for code in em.factor_codes():
            for t in range(n_quarters + 1):
                highlight_rows.append({
                    "company_id":      company_id,
                    "year":            year,
                    "scenario_id":     int(scen_idx),
                    "rank_type":       f"best_{rank}",
                    "rank_category":   "best",
                    "rank_order":      rank,
                    "factor_code":     code,
                    "period":          "Spot" if t == 0 else f"Q{t}",
                    "period_order":    t,
                    "value":           float(paths[code][scen_idx, t]),
                    "scenario_opcf":   float(cf_sim[scen_idx]),
                })
    df_highlight = pd.DataFrame(highlight_rows)
    _append_to_csv(df_highlight,
                   f"{output_dir}/highlight_scenarios.csv",
                   company_id, year)

    return {
        "companies":          f"{output_dir}/companies.csv",
        "summary":            f"{output_dir}/cfar_summary.csv",
        "scenarios":          f"{output_dir}/cfar_scenarios.csv",
        "decomposition":      f"{output_dir}/cfar_decomposition.csv",
        "factor_quantiles":   f"{output_dir}/factor_quantiles.csv",
        "highlight_scenarios":f"{output_dir}/highlight_scenarios.csv",
    }


def run(yaml_path: str, output_dir: str = "output"):
    print(f"\n{'═'*60}")
    print(f"  Cargando exposure map: {yaml_path}")
    print(f"{'═'*60}")

    em = ExposureMap.from_yaml(yaml_path)
    print(em.summary())

    print(f"\n  Cargando datos históricos...")
    df = load_historical_data(
        factor_codes = em.factor_codes(),
        start        = str(em.simulation_config["historical_data_window"]["start"]),
        end          = str(em.simulation_config["historical_data_window"]["end"]),
    )
    print(f"  → {len(df)} observaciones cargadas")

    print(f"\n  Simulando {em.simulation_config['n_scenarios']:,} escenarios...")
    paths, spots, log_ret = simulate_scenarios(
        df_historical = df,
        n_scenarios   = em.simulation_config["n_scenarios"],
        n_quarters    = em.horizon_quarters,
        seed          = em.simulation_config["seed"],
    )

    print(f"\n  Aplicando exposure map por línea P&L...")
    pl_impacts = calculate_pl_impacts(em, paths, spots)

    print(f"\n  Calculando coste de cobertura...")
    hedge_costs = calculate_hedge_costs(em, spots)
    for code in em.factor_codes():
        bps = em.get_exposure(code).parameters.get("hedge_cost_bps", 0)
        line = em.get_exposure(code).pl_line
        print(f"    {code:<12} {bps:>3} bp → {line:<16} "
              f"{em.functional_currency} {hedge_costs[code]:>8,.1f} mm")
    print(f"    {'TOTAL':<12}     →                 "
          f"{em.functional_currency} {hedge_costs['_total']:>8,.1f} mm")
    print(f"    Por línea P&L:")
    for line, val in hedge_costs["by_line"].items():
        if val > 0:
            print(f"      {line:<16} {em.functional_currency} {val:>8,.1f} mm")

    print(f"\n  Construyendo Operating CF simulado...")
    sim = build_simulated_cash_flow(em, pl_impacts, hedge_costs)

    # ── Postura B: target NETO del coste de cobertura ──────────────────────
    target_neto = build_target_with_hedge_only(em, hedge_costs)

    confidence = em.simulation_config["confidence_level"]
    cf = em.cash_flow_target  # target BRUTO (sin coste de cobertura)

    cfar_op_cf  = compute_at_risk(sim["operating_cf"], target_neto["operating_cf"], confidence)
    rev_at_risk = compute_at_risk(sim["revenue"],      target_neto["revenue"],      confidence)
    ebitda_risk = compute_at_risk(sim["ebitda"],       target_neto["ebitda"],       confidence)
    ebit_risk   = compute_at_risk(sim["ebit"],         target_neto["ebit"],         confidence)

    print(f"\n  ╔══════════════════════════════════════════════════════╗")
    print(f"  ║  Results — {em.company_name}")
    print(f"  ╠══════════════════════════════════════════════════════╣")
    print(f"  ║  Revenue at Risk (95%) :  €{rev_at_risk['at_risk']:>8,.0f} mm")
    print(f"  ║  EBITDA at Risk  (95%) :  €{ebitda_risk['at_risk']:>8,.0f} mm")
    print(f"  ║  EBIT at Risk    (95%) :  €{ebit_risk['at_risk']:>8,.0f} mm")
    print(f"  ║  CFaR            (95%) :  €{cfar_op_cf['at_risk']:>8,.0f} mm")
    print(f"  ║")
    print(f"  ║  Op. CF target bruto   :  €{cf.operating_cf:>8,.0f} mm")
    print(f"  ║  Op. CF target neto    :  €{target_neto['operating_cf']:>8,.0f} mm  (− coste cobertura)")
    print(f"  ║  Op. CF medio simulado :  €{cfar_op_cf['mean']:>8,.0f} mm")
    print(f"  ║  Op. CF Pct  5         :  €{cfar_op_cf['pct_5']:>8,.0f} mm")
    print(f"  ║  Op. CF Pct 95         :  €{cfar_op_cf['pct_95']:>8,.0f} mm")
    print(f"  ║  CFaR / Target neto    :  {cfar_op_cf['at_risk']/target_neto['operating_cf']:>8.1%}")
    print(f"  ╚══════════════════════════════════════════════════════╝")

    print(f"\n  Descomposición por línea P&L (impacto medio):")
    for line in ["revenue", "operating_costs", "taxes", "wc_change"]:
        impact = pl_impacts["by_line"][line]
        print(f"    {line:<18} media = {np.mean(impact):>+10,.0f}  "
              f"σ = {np.std(impact):>10,.0f}")

    print(f"\n  Descomposición por factor (anual):")
    for code in em.factor_codes():
        ann = pl_impacts["by_factor"][code]["_annual"]
        exp = em.get_exposure(code)
        print(f"    {code:<12} → {exp.pl_line:<16}  "
              f"media = {np.mean(ann):>+10,.0f}  σ = {np.std(ann):>9,.0f}")

    files = export_results(em, paths, spots, sim, pl_impacts,
                            hedge_costs, cfar_op_cf, target_neto, output_dir)
    plot_path = plot_cfar(em, paths, sim, cfar_op_cf, output_dir)

    print(f"\n  Outputs:")
    for k, v in files.items():
        print(f"    {k} → {v}")
    print(f"    plot → {plot_path}")

    return em, cfar_op_cf, pl_impacts


if __name__ == "__main__":
    yaml_path = sys.argv[1] if len(sys.argv) > 1 else "iag_2026.yaml"
    run(yaml_path)