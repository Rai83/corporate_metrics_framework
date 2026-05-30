"""
frontier.py
═══════════════════════════════════════════════════════════════════════════
Calcula la frontera eficiente de cobertura para una empresa.

Estrategia (Common Random Numbers):
  1. Genera los paths Monte Carlo UNA sola vez con n_scenarios escenarios.
  2. Calcula los impactos brutos (sin hedge) por factor, trimestre y escenario.
  3. Para cada combinación de hedge ratios:
     - Escala los impactos brutos por (1 - h_i)
     - Construye el cash flow simulado y calcula CFaR + coste cobertura
  4. Filtra los puntos eficientes (frontera de Pareto).
  5. Exporta CSV y genera gráfico.

El uso de los mismos shocks aleatorios para todas las combinaciones cancela
el ruido Monte Carlo entre puntos, produciendo una frontera suave y
comparable.

Uso:
  python -m src.frontier config/exposure_maps/iag_2026.yaml
  python -m src.frontier config/exposure_maps/iag_2026.yaml --grid 21
"""
import argparse
import itertools
import time
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from src.exposure_mappings.cfar import (
    load_historical_data,
    simulate_scenarios,
    compute_at_risk,
)
from src.exposure_mappings.exposure_map import ExposureMap, VALID_PL_LINES
from src.reporting.theme import (
    NAVY, GREY_DARK, GREY_MEDIUM, GREY_LIGHT, RED, apply_theme,
    fmt_eur_mm, fmt_number,
)


# ═══════════════════════════════════════════════════════════════════════════
# 1. PRECÁLCULO DE IMPACTOS BRUTOS (sin hedge)
# ═══════════════════════════════════════════════════════════════════════════
def precompute_factor_impacts(em: ExposureMap, paths: dict, spots: dict) -> dict:
    """
    Calcula los impactos brutos (con hedge_ratio = 0) por factor y trimestre.
    Esto se ejecuta UNA sola vez. Después solo hay que escalar por (1 - h).

    IMPORTANTE: esta función SOLO soporta función de tipo 'linear' por ahora.
    Las funciones 'stepped' y 'econometric' no se pueden precalcular del mismo
    modo, porque el hedge no es proporcional al impacto.

    Devuelve dict con estructura:
      raw[factor_code]['by_quarter'][t]  → array (n_scenarios,) impacto bruto
      raw[factor_code]['annual']         → array (n_scenarios,) suma anual
      raw[factor_code]['pl_line']        → línea P&L del factor
    """
    n_quarters = em.horizon_quarters

    raw = {}
    for exp in em.exposures:
        if exp.function_type != "linear":
            raise NotImplementedError(
                f"Frontera eficiente solo soporta función 'linear' por ahora. "
                f"El factor '{exp.factor_code}' usa '{exp.function_type}'."
            )

        factor_paths = paths[exp.factor_code]
        spot         = spots[exp.factor_code]
        quantity     = exp.parameters["quantity"]
        sign         = exp.parameters.get("sign", 1)
        inverse_rate = exp.parameters.get("inverse_rate", False)
        distribution = exp.parameters.get(
            "quarterly_distribution",
            [1.0 / n_quarters] * n_quarters
        )

        # Conversión FX (opcional)
        currency_conv = exp.parameters.get("currency_conversion")
        if currency_conv:
            conv_paths = paths[currency_conv["factor_code"]]
            conv_type  = currency_conv.get("type", "divide")
        else:
            conv_paths = None
            conv_type  = None

        by_quarter = {}
        annual = np.zeros_like(factor_paths[:, 0])

        for t in range(n_quarters):
            quantity_q = quantity * distribution[t]
            factor_q   = factor_paths[:, t + 1]

            # Delta efectivo (sin hedge_ratio aplicado)
            if inverse_rate:
                delta_efectivo = 1.0 / factor_q - 1.0 / spot
            else:
                delta_efectivo = factor_q - spot

            # Impacto bruto: sign × cantidad_Q × Δprecio (sin hedge)
            impact_raw = sign * quantity_q * delta_efectivo

            # Conversión FX si aplica
            if conv_paths is not None:
                conv_q = conv_paths[:, t + 1]
                impact_raw = (impact_raw / conv_q if conv_type == "divide"
                              else impact_raw * conv_q)

            by_quarter[t] = impact_raw
            annual = annual + impact_raw

        raw[exp.factor_code] = {
            "by_quarter": by_quarter,
            "annual":     annual,
            "pl_line":    exp.pl_line,
        }

    return raw


# ═══════════════════════════════════════════════════════════════════════════
# 2. PRECÁLCULO DE COSTES UNITARIOS DE COBERTURA
# ═══════════════════════════════════════════════════════════════════════════
def precompute_hedge_unit_costs(em: ExposureMap, spots: dict) -> dict:
    """
    Calcula el 'coste unitario' de cobertura por factor — es decir, el coste
    correspondiente a hedge_ratio = 1.0. Después, para cualquier ratio h, el
    coste real es:  cost = unit_cost × h.

    Devuelve dict {factor_code: unit_cost} y by_line {pl_line: unit_cost_total}
    """
    unit_costs = {"_by_factor": {}, "_by_line": {line: 0.0 for line in VALID_PL_LINES}}

    for exp in em.exposures:
        bps = exp.parameters.get("hedge_cost_bps", 0)
        if bps == 0:
            unit_costs["_by_factor"][exp.factor_code] = 0.0
            continue

        quantity     = exp.parameters["quantity"]
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

        unit_cost = value_functional * (bps / 10000.0)
        unit_costs["_by_factor"][exp.factor_code] = unit_cost
        unit_costs["_by_line"][exp.pl_line] += unit_cost

    return unit_costs


# ═══════════════════════════════════════════════════════════════════════════
# 3. EVALUACIÓN DE UNA COMBINACIÓN DE HEDGE RATIOS
# ═══════════════════════════════════════════════════════════════════════════
def evaluate_combination(em: ExposureMap,
                         raw_impacts: dict,
                         unit_costs: dict,
                         hedge_ratios: dict,
                         confidence: float = 0.95) -> dict:
    """
    Evalúa una combinación específica de hedge ratios.

    `hedge_ratios` es un dict {factor_code: h} con valores en [0, 1].
    """
    # ── 1. Aplicar hedge ratios a los impactos brutos ──────────────────────
    pl_impacts_by_line = {line: 0.0 for line in VALID_PL_LINES}
    for code, raw in raw_impacts.items():
        h = hedge_ratios[code]
        # impacto con hedge = impacto bruto × (1 - h)
        annual_with_hedge = raw["annual"] * (1.0 - h)
        pl_impacts_by_line[raw["pl_line"]] = (
            pl_impacts_by_line[raw["pl_line"]] + annual_with_hedge
        )

    # ── 2. Calcular coste de cobertura ─────────────────────────────────────
    hedge_cost_by_line = {line: 0.0 for line in VALID_PL_LINES}
    hedge_cost_total = 0.0
    for code, unit in unit_costs["_by_factor"].items():
        h = hedge_ratios[code]
        cost = unit * h
        exp = em.get_exposure(code)
        hedge_cost_by_line[exp.pl_line] += cost
        hedge_cost_total += cost

    # ── 3. Construir el cash flow simulado ─────────────────────────────────
    cf = em.cash_flow_target

    revenue_sim = (cf.revenue
                   + pl_impacts_by_line["revenue"]
                   - hedge_cost_by_line["revenue"])
    operating_costs_sim = (cf.operating_costs
                           + pl_impacts_by_line["operating_costs"]
                           + hedge_cost_by_line["operating_costs"])

    ebitda_sim = revenue_sim - operating_costs_sim
    ebit_sim   = ebitda_sim - cf.depreciation_amortization

    taxes_sim = (ebit_sim * em.tax_rate
                 + pl_impacts_by_line["taxes"]
                 + hedge_cost_by_line["taxes"])

    nopat_sim = ebit_sim - taxes_sim

    operating_cf_sim = (nopat_sim
                        + cf.depreciation_amortization
                        + cf.wc_change
                        + pl_impacts_by_line["wc_change"])

    # ── 4. Calcular target NETO (sólo con este coste de cobertura) ─────────
    rev_neto    = cf.revenue          - hedge_cost_by_line["revenue"]
    opex_neto   = cf.operating_costs  + hedge_cost_by_line["operating_costs"]
    ebitda_neto = rev_neto - opex_neto
    ebit_neto   = ebitda_neto - cf.depreciation_amortization
    taxes_neto  = ebit_neto * em.tax_rate + hedge_cost_by_line["taxes"]
    nopat_neto  = ebit_neto - taxes_neto
    opcf_neto   = nopat_neto + cf.depreciation_amortization + cf.wc_change

    # ── 5. Métricas at-risk ────────────────────────────────────────────────
    cfar_metrics = compute_at_risk(operating_cf_sim, opcf_neto, confidence)

    return {
        "hedge_ratios":      dict(hedge_ratios),
        "hedge_cost_total":  hedge_cost_total,
        "hedge_cost_neto":   hedge_cost_total * (1 - em.tax_rate),
        "opcf_target_neto":  opcf_neto,
        "opcf_mean":         cfar_metrics["mean"],
        "opcf_pct5":         cfar_metrics["pct_5"],
        "opcf_pct95":        cfar_metrics["pct_95"],
        "cfar_95":           cfar_metrics["at_risk"],
        "cfar_pct_target":   cfar_metrics["at_risk"] / opcf_neto,
    }


# ═══════════════════════════════════════════════════════════════════════════
# 4. FILTRO DE PARETO — extraer la frontera eficiente
# ═══════════════════════════════════════════════════════════════════════════
def filter_pareto_front(points: list, x_key: str = "cfar_95",
                        y_key: str = "hedge_cost_total") -> list:
    """
    Filtra puntos no dominados. Un punto P es dominado si existe otro punto Q
    con:  Q[x] ≤ P[x]  Y  Q[y] ≤ P[y]  con al menos una desigualdad estricta.

    Tanto x_key como y_key son "a minimizar" — menos CFaR mejor, menos coste mejor.
    """
    sorted_pts = sorted(points, key=lambda p: (p[x_key], p[y_key]))

    frontier = []
    best_y = float("inf")
    for p in sorted_pts:
        if p[y_key] < best_y - 1e-9:
            frontier.append(p)
            best_y = p[y_key]

    return frontier


# ═══════════════════════════════════════════════════════════════════════════
# 5. ORQUESTADOR
# ═══════════════════════════════════════════════════════════════════════════
def compute_frontier(em: ExposureMap, n_grid: int = 11) -> dict:
    """
    Calcula la frontera completa para una empresa.

    `n_grid` es el número de puntos por factor en el grid (11 → 0%, 10%, ..., 100%).
    """
    factor_codes = em.factor_codes()
    n_factors = len(factor_codes)

    # ── 1. Cargar datos históricos ─────────────────────────────────────────
    print(f"\n  Cargando datos históricos...")
    start = em.simulation_config["historical_data_window"]["start"]
    end   = em.simulation_config["historical_data_window"]["end"]
    df_hist = load_historical_data(factor_codes, start, end)
    print(f"  → {len(df_hist)} observaciones cargadas")

    # ── 2. Simular paths UNA SOLA VEZ ──────────────────────────────────────
    n_scenarios = em.simulation_config["n_scenarios"]
    n_quarters  = em.horizon_quarters
    print(f"\n  Simulando {n_scenarios:,} escenarios (una sola vez)...")
    paths, spots, _ = simulate_scenarios(
        df_hist,
        n_scenarios=n_scenarios,
        n_quarters=n_quarters,
        seed=em.simulation_config.get("seed", 42),
    )

    # ── 3. Precalcular impactos brutos y costes unitarios ──────────────────
    print(f"\n  Precalculando impactos brutos por factor...")
    raw_impacts = precompute_factor_impacts(em, paths, spots)
    unit_costs  = precompute_hedge_unit_costs(em, spots)

    print(f"  Coste unitario por factor (hedge ratio = 100%):")
    for code, cost in unit_costs["_by_factor"].items():
        print(f"    {code:<12} → EUR {cost:>7,.1f} mm")

    # ── 4. Grid search sobre el espacio de hedge ratios ────────────────────
    grid_values = np.linspace(0.0, 1.0, n_grid)
    total_combos = n_grid ** n_factors
    print(f"\n  Evaluando grid: {n_grid} valores × {n_factors} factores "
          f"= {total_combos:,} combinaciones...")

    t0 = time.time()
    all_points = []

    for i, combo in enumerate(itertools.product(grid_values, repeat=n_factors)):
        hedge_ratios = dict(zip(factor_codes, combo))
        result = evaluate_combination(em, raw_impacts, unit_costs, hedge_ratios,
                                       confidence=em.simulation_config["confidence_level"])
        all_points.append(result)

        if (i + 1) % max(1, total_combos // 10) == 0:
            elapsed = time.time() - t0
            pct = (i + 1) / total_combos * 100
            print(f"    {pct:>5.0f}% ({i+1:,}/{total_combos:,}) — {elapsed:.1f}s")

    elapsed_total = time.time() - t0
    print(f"  Grid evaluado en {elapsed_total:.1f}s "
          f"({elapsed_total/total_combos*1000:.1f} ms/punto)")

    # ── 5. Filtrar frontera de Pareto ──────────────────────────────────────
    print(f"\n  Extrayendo frontera de Pareto...")
    frontier = filter_pareto_front(all_points,
                                    x_key="cfar_95",
                                    y_key="hedge_cost_total")
    print(f"  → {len(frontier)} puntos eficientes "
          f"({len(frontier)/total_combos*100:.1f}% del grid)")

    # ── 6. Punto actual de la empresa (los ratios del exposure map) ────────
    current_ratios = {exp.factor_code: exp.parameters["hedge_ratio"]
                      for exp in em.exposures}
    current_point = evaluate_combination(em, raw_impacts, unit_costs, current_ratios,
                                          confidence=em.simulation_config["confidence_level"])

    return {
        "all_points":      all_points,
        "frontier":        frontier,
        "current_point":   current_point,
        "factor_codes":    factor_codes,
        "grid_values":     grid_values.tolist(),
    }


# ═══════════════════════════════════════════════════════════════════════════
# 6. EXPORTACIÓN A CSV
# ═══════════════════════════════════════════════════════════════════════════
def export_frontier(result: dict, em: ExposureMap, output_dir: str = "output"):
    """Exporta los puntos del grid y los de la frontera a CSV."""
    company = em.company_code
    year    = em.reporting_period
    factor_codes = result["factor_codes"]

    # Construir DataFrame de todos los puntos
    rows = []
    frontier_keys = set()
    for p in result["frontier"]:
        # Identificar puntos eficientes por tupla de ratios redondeados
        key = tuple(round(p["hedge_ratios"][c], 4) for c in factor_codes)
        frontier_keys.add(key)

    for p in result["all_points"]:
        key = tuple(round(p["hedge_ratios"][c], 4) for c in factor_codes)
        row = {
            "company_id":         company,
            "year":               year,
            "is_efficient":       key in frontier_keys,
            "hedge_cost_total":   p["hedge_cost_total"],
            "hedge_cost_neto":    p["hedge_cost_neto"],
            "cfar_95":            p["cfar_95"],
            "cfar_pct_target":    p["cfar_pct_target"],
            "opcf_target_neto":   p["opcf_target_neto"],
            "opcf_mean":          p["opcf_mean"],
            "opcf_pct5":          p["opcf_pct5"],
        }
        for c in factor_codes:
            row[f"hedge_{c}"] = p["hedge_ratios"][c]
        rows.append(row)

    df = pd.DataFrame(rows)
    csv_path = f"{output_dir}/{company.lower()}_frontier_{year}.csv"
    df.to_csv(csv_path, index=False, sep=",", decimal=".")
    print(f"  CSV exportado: {csv_path}")

    return csv_path


# ═══════════════════════════════════════════════════════════════════════════
# 7. GRÁFICO DE LA FRONTERA — DOS PANELES + CASCO CONVEXO
# ═══════════════════════════════════════════════════════════════════════════
def _compute_lower_convex_hull(points: list,
                               x_key: str = "cfar_95",
                               y_key: str = "hedge_cost_total") -> list:
    """
    Calcula la envolvente convexa inferior (lower-left convex hull) de un
    conjunto de puntos. Es la frontera "verdadera" suavizada, sin escalones.

    Algoritmo: monotone chain (Andrew's algorithm). Ordena los puntos por X,
    y construye el hull manteniendo solo los puntos con giros a la izquierda.
    """
    pts = sorted(points, key=lambda p: (p[x_key], p[y_key]))
    if len(pts) <= 2:
        return pts

    def cross(O, A, B):
        return ((A[x_key] - O[x_key]) * (B[y_key] - O[y_key])
                - (A[y_key] - O[y_key]) * (B[x_key] - O[x_key]))

    hull = []
    for p in pts:
        # Quitar puntos del hull mientras hagan giro a la derecha (convexidad)
        while len(hull) >= 2 and cross(hull[-2], hull[-1], p) >= 0:
            hull.pop()
        hull.append(p)
    return hull


def plot_frontier(result: dict, em: ExposureMap, output_dir: str = "output"):
    apply_theme()

    company   = em.company_code
    year      = em.reporting_period

    all_pts   = result["all_points"]
    frontier  = result["frontier"]
    current   = result["current_point"]
    factor_codes = result["factor_codes"]

    # ── 1. ORDENAR LA FRONTERA POR CFaR ────────────────────────────────────
    frontier_sorted = sorted(frontier, key=lambda p: p["cfar_95"])

    # Coste máximo posible (cobertura 100% en todos los factores)
    max_cost = max(p["hedge_cost_total"] for p in all_pts)

    # ── 2. CREAR FIGURA — un solo panel ───────────────────────────────────
    fig, ax_top = plt.subplots(figsize=(13, 7))
    fig.subplots_adjust(top=0.92, bottom=0.12, left=0.08, right=0.92)

    # Frontera completa — solo puntos, sin línea, sin sombreado
    x_fr = [p["cfar_95"] for p in frontier_sorted]
    y_fr = [p["hedge_cost_total"] for p in frontier_sorted]
    ax_top.scatter(x_fr, y_fr, s=22, color=NAVY, zorder=4,
                   edgecolor="white", linewidth=0.4,
                   label=f"Frontera eficiente ({len(frontier_sorted)} puntos)")

    # Punto IAG actual
    ax_top.scatter([current["cfar_95"]], [current["hedge_cost_total"]],
                   s=220, color=RED, zorder=6, marker="D",
                   edgecolor="white", linewidth=1.8,
                   label=f"Posición actual {company}")

    # Anotación IAG con valores
    ax_top.annotate(
        f"{company}\n"
        f"CFaR: {fmt_eur_mm(current['cfar_95'])}\n"
        f"Coste: {fmt_eur_mm(current['hedge_cost_total'])}",
        xy=(current["cfar_95"], current["hedge_cost_total"]),
        xytext=(20, 12), textcoords="offset points",
        fontsize=9.5, color=RED, weight="bold", va="bottom",
        bbox=dict(boxstyle="round,pad=0.4", facecolor="white",
                  edgecolor=RED, alpha=0.95, linewidth=1.2),
    )

    # Etiquetas de los extremos
    extreme_no_hedge = frontier_sorted[-1]
    ax_top.annotate("Sin cobertura\n(0%)",
                    xy=(extreme_no_hedge["cfar_95"],
                        extreme_no_hedge["hedge_cost_total"]),
                    xytext=(-15, 35), textcoords="offset points",
                    fontsize=8.5, color=GREY_DARK, style="italic",
                    ha="right")
    extreme_full = frontier_sorted[0]
    ax_top.annotate("Cobertura\ntotal (100%)",
                    xy=(extreme_full["cfar_95"],
                        extreme_full["hedge_cost_total"]),
                    xytext=(20, -10), textcoords="offset points",
                    fontsize=8.5, color=GREY_DARK, style="italic",
                    ha="left")

    ax_top.set_ylabel("Coste anual de cobertura (€ millones)",
                      fontsize=10.5, color=NAVY)
    ax_top.set_title(f"Frontera eficiente de cobertura — {em.company_name} {year}",
                     loc="left", color=NAVY, pad=14, fontsize=14, weight="bold")
    ax_top.xaxis.set_major_formatter(plt.FuncFormatter(lambda x, _: fmt_number(x)))
    ax_top.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, _: fmt_number(x)))
    ax_top.grid(alpha=0.35)
    ax_top.legend(loc="upper right", framealpha=0.95, edgecolor=GREY_LIGHT,
                  fontsize=9)

    # ── EJE DERECHO: % efectivo de cobertura ───────────────────────────────
    ax_right = ax_top.twinx()
    ax_right.set_ylim(ax_top.get_ylim())
    # Convertir el eje de coste a % del coste máximo
    yticks_pct = [0, 0.20, 0.40, 0.60, 0.80, 1.0]
    yticks_eur = [t * max_cost for t in yticks_pct]
    ax_right.set_yticks(yticks_eur)
    ax_right.set_yticklabels([f"{p*100:.0f}%" for p in yticks_pct])
    ax_right.set_ylabel("% de cobertura efectiva\n(coste / coste máximo)",
                        fontsize=10.5, color=GREY_DARK, rotation=270,
                        labelpad=28)
    ax_right.tick_params(axis="y", colors=GREY_DARK, labelsize=9)
    ax_right.spines["right"].set_color(GREY_LIGHT)

    # ── Eje X del panel superior (ahora es el único panel) ─────────────────
    ax_top.set_xlabel("CFaR 95% (€ millones)", fontsize=10.5, color=NAVY)
    ax_top.tick_params(labelbottom=True)

    # ── Texto interpretativo abajo ─────────────────────────────────────────
    fig.text(0.5, 0.025,
             f"Frontera eficiente de Pareto ({len(frontier_sorted)} puntos no dominados). "
             "Cada punto representa una combinación óptima de ratios de cobertura "
             "de los factores de riesgo.",
             fontsize=8.5, color=GREY_MEDIUM, style="italic",
             ha="center", va="bottom")

    png_path = f"{output_dir}/{company.lower()}_frontier_{year}.png"
    plt.savefig(png_path, dpi=150, bbox_inches="tight",
                facecolor="white")
    plt.close(fig)
    print(f"  Gráfico exportado: {png_path}")

    return png_path


# ═══════════════════════════════════════════════════════════════════════════
# 8. CLI
# ═══════════════════════════════════════════════════════════════════════════
def run(yaml_path: str, n_grid: int = 11, output_dir: str = "output"):
    """Pipeline completo: carga YAML, calcula frontera, exporta CSV y PNG."""
    import os
    os.makedirs(output_dir, exist_ok=True)

    print("═" * 64)
    print(f"  FRONTERA EFICIENTE DE COBERTURA")
    print(f"  Cargando exposure map: {Path(yaml_path).name}")
    print("═" * 64)

    em = ExposureMap.from_yaml(yaml_path)
    print(f"  Empresa     : {em.company_name} ({em.company_code})")
    print(f"  Periodo     : {em.reporting_period}")
    print(f"  Factores    : {', '.join(em.factor_codes())}")

    t_total = time.time()
    result = compute_frontier(em, n_grid=n_grid)

    print(f"\n  RESUMEN DE LA FRONTERA")
    print(f"  ─────────────────────────────────────────────")

    # Extremos
    if len(result["frontier"]) > 0:
        max_cfar = max(result["frontier"], key=lambda p: p["cfar_95"])
        min_cfar = min(result["frontier"], key=lambda p: p["cfar_95"])
        print(f"  Punto sin cobertura: CFaR = {fmt_eur_mm(max_cfar['cfar_95'])}, "
              f"coste = {fmt_eur_mm(max_cfar['hedge_cost_total'])}")
        print(f"  Punto máx. cobertura: CFaR = {fmt_eur_mm(min_cfar['cfar_95'])}, "
              f"coste = {fmt_eur_mm(min_cfar['hedge_cost_total'])}")

    # Posición actual
    curr = result["current_point"]
    print(f"\n  Posición actual de {em.company_code}:")
    for c in result["factor_codes"]:
        print(f"    hedge_{c:<12} = {curr['hedge_ratios'][c]:>5.0%}")
    print(f"    CFaR  : {fmt_eur_mm(curr['cfar_95'])}")
    print(f"    Coste : {fmt_eur_mm(curr['hedge_cost_total'])}")

    # ¿Es eficiente la posición actual?
    is_current_eff = any(
        all(abs(p["hedge_ratios"][c] - curr["hedge_ratios"][c]) < 0.05
            for c in result["factor_codes"])
        for p in result["frontier"]
    )
    print(f"    ¿Es eficiente?: "
          f"{'sí (en la frontera)' if is_current_eff else 'NO (dominada)'}")

    # ── Exportar ───────────────────────────────────────────────────────────
    print(f"\n  Exportando resultados a {output_dir}/...")
    csv_path = export_frontier(result, em, output_dir)
    png_path = plot_frontier(result, em, output_dir)

    elapsed = time.time() - t_total
    print(f"\n  Frontera completa generada en {elapsed:.1f}s")
    print("═" * 64)

    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Calcula la frontera eficiente de cobertura")
    parser.add_argument("yaml_path", help="Path del exposure map YAML")
    parser.add_argument("--grid", type=int, default=11,
                        help="Número de valores por factor en el grid (default: 11)")
    parser.add_argument("--output-dir", default="output",
                        help="Directorio de salida (default: output)")
    args = parser.parse_args()

    run(args.yaml_path, n_grid=args.grid, output_dir=args.output_dir)