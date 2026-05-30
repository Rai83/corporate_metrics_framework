"""
pages.py
═══════════════════════════════════════════════════════════════════════════
Cada función de página recibe los datos preparados y devuelve una `Figure`.
"""
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.patches as patches
from matplotlib.gridspec import GridSpec

from .theme import (
    PAGE_W, PAGE_H,
    BLACK, NAVY, BLUE_PRIMARY, BLUE_LIGHT, BLUE_PALE,
    GREY_DARK, GREY_MEDIUM, GREY_LIGHT, GREY_PALE,
    RED, GREEN, AMBER,
    fmt_eur_mm, fmt_pct, fmt_number,
)
from .components import (
    draw_page_header, draw_page_footer,
    draw_kpi_card, draw_callout, draw_table,
)


# ═══════════════════════════════════════════════════════════════════════════
# PÁGINA 1 — PORTADA
# ═══════════════════════════════════════════════════════════════════════════
def page_cover(company_name: str, year: int,
               summary: pd.Series, total_pages: int,
               author: str = "", date_str: str = "") -> plt.Figure:
    fig = plt.figure(figsize=(PAGE_W, PAGE_H))

    # Banda superior decorativa
    fig.patches.append(patches.Rectangle(
        (0, 0.85), 1, 0.15,
        transform=fig.transFigure,
        facecolor=NAVY, edgecolor="none"
    ))
    # Banda inferior decorativa fina
    fig.patches.append(patches.Rectangle(
        (0, 0), 1, 0.04,
        transform=fig.transFigure,
        facecolor=BLUE_PRIMARY, edgecolor="none"
    ))

    # Título principal
    fig.text(0.5, 0.92, "Cash Flow at Risk",
             fontsize=28, color="white", weight="bold",
             ha="center", va="center")

    # Subtítulo dentro de banda
    fig.text(0.5, 0.875, "CorporateMetrics framework",
             fontsize=12, color=BLUE_PALE, style="italic",
             ha="center", va="center")

    # Empresa y año (grandes, en el centro de la página)
    fig.text(0.5, 0.72, company_name,
             fontsize=24, color=NAVY, weight="bold",
             ha="center", va="center")
    fig.text(0.5, 0.66, f"Ejercicio {year}",
             fontsize=16, color=GREY_DARK,
             ha="center", va="center")

    # 4 KPIs grandes
    target  = summary["opcf_target"]
    cfar    = summary["cfar_95"]
    cfar_pc = summary["cfar_pct_target"]
    pct5    = summary["opcf_pct5"]

    card_w = 0.18
    card_h = 0.16
    card_y = 0.32
    gap    = 0.02
    total  = 4 * card_w + 3 * gap
    start_x = (1 - total) / 2

    draw_kpi_card(fig, start_x + 0*(card_w+gap), card_y, card_w, card_h,
                  "Operating CF Target", fmt_eur_mm(target))
    draw_kpi_card(fig, start_x + 1*(card_w+gap), card_y, card_w, card_h,
                  "CFaR (95%)", fmt_eur_mm(cfar),
                  color=NAVY, accent=True,
                  sublabel=f"{fmt_pct(cfar_pc)} del target")
    draw_kpi_card(fig, start_x + 2*(card_w+gap), card_y, card_w, card_h,
                  "Operating CF — Pct 5", fmt_eur_mm(pct5))
    draw_kpi_card(fig, start_x + 3*(card_w+gap), card_y, card_w, card_h,
                  "Horizonte", "4 trimestres",
                  sublabel="Confianza 95%")

    # Pie de portada
    if author:
        fig.text(0.5, 0.18, author,
                 fontsize=11, color=GREY_DARK,
                 ha="center", va="center")
    if date_str:
        fig.text(0.5, 0.14, date_str,
                 fontsize=10, color=GREY_MEDIUM,
                 ha="center", va="center")

    fig.text(0.5, 0.08,
             "Simulación Monte Carlo · 10.000 escenarios · "
             "datos de mercado 2019–2024",
             fontsize=9, color=GREY_MEDIUM, style="italic",
             ha="center", va="center")

    return fig


# ═══════════════════════════════════════════════════════════════════════════
# PÁGINA 2 — DISTRIBUCIÓN DEL OPERATING CASH FLOW
# ═══════════════════════════════════════════════════════════════════════════
def page_distribution(company_name: str, year: int,
                      summary: pd.Series, scenarios: pd.DataFrame,
                      page_num: int, total_pages: int) -> plt.Figure:
    fig = plt.figure(figsize=(PAGE_W, PAGE_H))

    draw_page_header(fig,
        title="Distribución del Operating Cash Flow",
        subtitle=f"{company_name} · Ejercicio {year}",
        page_num=page_num, total_pages=total_pages)

    # Layout: histograma grande arriba, callout abajo
    gs = GridSpec(2, 1, figure=fig,
                  height_ratios=[3, 1],
                  top=0.88, bottom=0.07, left=0.07, right=0.96,
                  hspace=0.35)

    ax = fig.add_subplot(gs[0])
    cf       = scenarios["operating_cf"].values
    target   = summary["opcf_target"]
    mean_cf  = summary["opcf_mean"]
    pct5     = summary["opcf_pct5"]
    pct95    = summary["opcf_pct95"]
    cfar     = summary["cfar_95"]

    # Histograma
    n, bins, patches_list = ax.hist(
        cf, bins=80,
        color=BLUE_LIGHT, edgecolor="white", linewidth=0.4,
        density=False, zorder=2
    )
    # Colorear la cola izquierda (peor 5%)
    for p, left in zip(patches_list, bins[:-1]):
        if left < pct5:
            p.set_facecolor("#F4B6B6")

    # Sombreado del peor 5%
    ax.axvspan(cf.min(), pct5, alpha=0.06, color=RED, zorder=1)

    # Líneas verticales
    ax.axvline(target,  color=GREEN,        linewidth=2.0,
               linestyle="--", zorder=4, label=f"Target: {fmt_eur_mm(target)}")
    ax.axvline(mean_cf, color=NAVY,         linewidth=1.8,
               linestyle="-",  zorder=4, label=f"Media: {fmt_eur_mm(mean_cf)}")
    ax.axvline(pct5,    color=RED,          linewidth=1.6,
               linestyle="--", zorder=4, label=f"Pct 5: {fmt_eur_mm(pct5)}")
    ax.axvline(pct95,   color=AMBER,        linewidth=1.4,
               linestyle="--", zorder=4, label=f"Pct 95: {fmt_eur_mm(pct95)}")

    # Flecha del CFaR
    y_top = n.max()
    y_arrow = y_top * 0.85
    ax.annotate("", xy=(pct5, y_arrow), xytext=(target, y_arrow),
                arrowprops=dict(arrowstyle="<->", color=RED, lw=1.5))
    ax.text((pct5 + target) / 2, y_arrow * 1.04,
            f"CFaR (95%) = {fmt_eur_mm(cfar)}",
            ha="center", va="bottom", fontsize=11,
            color=RED, weight="bold")

    ax.set_title("Distribución empírica del Operating Cash Flow simulado",
                 loc="left", color=NAVY, pad=10)
    ax.set_xlabel("Operating Cash Flow (€ millones)")
    ax.set_ylabel("Frecuencia (número de escenarios)")
    ax.xaxis.set_major_formatter(plt.FuncFormatter(
        lambda x, _: f"{fmt_number(x)}"))
    ax.legend(loc="upper left", framealpha=0.95, edgecolor=GREY_LIGHT)
    ax.grid(axis="y", alpha=0.5)

    # Callout interpretativo
    body = (
        f"El CFaR del {fmt_pct(summary['cfar_pct_target'])} indica que, en el peor 5% de "
        f"los escenarios simulados, el cash flow operativo podría situarse por "
        f"debajo de {fmt_eur_mm(pct5)}, una desviación máxima de {fmt_eur_mm(cfar)} "
        f"respecto al target. La media simulada ({fmt_eur_mm(mean_cf)}) refleja el "
        f"equilibrio entre el drift histórico de los factores, los costes de "
        f"cobertura y el efecto fiscal amortiguador."
    )
    draw_callout(fig, 0.07, 0.07, 0.86, 0.18,
                 title="Lectura del CFaR",
                 body=body)

    return fig


# ═══════════════════════════════════════════════════════════════════════════
# PÁGINA 3 — CASCADA DE RIESGO P&L
# ═══════════════════════════════════════════════════════════════════════════
def page_pl_cascade(company_name: str, year: int,
                    summary: pd.Series, scenarios: pd.DataFrame,
                    page_num: int, total_pages: int) -> plt.Figure:
    fig = plt.figure(figsize=(PAGE_W, PAGE_H))

    draw_page_header(fig,
        title="Cascada del riesgo a través de la P&L",
        subtitle=f"{company_name} · Ejercicio {year}",
        page_num=page_num, total_pages=total_pages)

    # Calcular percentiles 5 de cada nivel de la P&L
    pct5_revenue = np.percentile(scenarios["revenue"], 5)
    pct5_ebitda  = np.percentile(scenarios["ebitda"],  5)
    pct5_ebit    = np.percentile(scenarios["ebit"],    5)
    pct5_opcf    = np.percentile(scenarios["operating_cf"], 5)

    rev_at_risk    = summary["revenue_target"]      - pct5_revenue
    ebitda_at_risk = summary["ebitda_target"]       - pct5_ebitda
    ebit_at_risk   = summary["ebit_target"]         - pct5_ebit
    cfar           = summary["cfar_95"]

    # Layout: gráfico de cascada arriba, tabla abajo
    gs = GridSpec(2, 1, figure=fig,
                  height_ratios=[2, 1.2],
                  top=0.88, bottom=0.06, left=0.07, right=0.96,
                  hspace=0.45)

    # ── Cascada visual ─────────────────────────────────────────────────────
    ax = fig.add_subplot(gs[0])

    metrics = ["Revenue\nat Risk", "EBITDA\nat Risk", "EBIT\nat Risk", "CFaR (95%)"]
    values  = [rev_at_risk, ebitda_at_risk, ebit_at_risk, cfar]
    colors  = [BLUE_LIGHT, BLUE_PRIMARY, NAVY, RED]

    x_pos = np.arange(len(metrics))
    bars = ax.bar(x_pos, values, width=0.55,
                  color=colors, edgecolor="white", linewidth=1.5)

    # Etiquetas con valores
    for bar, val in zip(bars, values):
        height = bar.get_height()
        ax.text(bar.get_x() + bar.get_width() / 2, height + max(values) * 0.02,
                fmt_eur_mm(val),
                ha="center", va="bottom",
                fontsize=11, color=NAVY, weight="bold")

    # Flechas conectando las etapas
    arrow_y = max(values) * 1.18
    for i in range(len(metrics) - 1):
        ax.annotate("", xy=(i + 1 - 0.3, arrow_y), xytext=(i + 0.3, arrow_y),
                    arrowprops=dict(arrowstyle="->", color=GREY_MEDIUM,
                                    lw=1.2, ls="--"))

    # Etiqueta del efecto amortiguador entre EBIT at Risk y CFaR
    diff = ebit_at_risk - cfar
    ax.text(2.5, arrow_y * 1.08,
            f"− {fmt_eur_mm(diff)}\n(efecto fiscal)",
            ha="center", va="bottom",
            fontsize=9, color=GREEN, style="italic")

    ax.set_xticks(x_pos)
    ax.set_xticklabels(metrics, fontsize=10)
    ax.set_ylabel("Desviación adversa máxima (€ mm)")
    ax.set_title("Transmisión del riesgo desde Revenue hasta el Cash Flow",
                 loc="left", color=NAVY, pad=10)
    ax.set_ylim(0, max(values) * 1.35)
    ax.yaxis.set_major_formatter(plt.FuncFormatter(
        lambda x, _: f"{fmt_number(x)}"))
    ax.grid(axis="y", alpha=0.5)

    # ── Tabla resumen ──────────────────────────────────────────────────────
    ax_tab = fig.add_subplot(gs[1])

    cols = ["Métrica", "Target", "Pct 5 simulado", "Desviación", "% sobre target"]
    rows = [
        ["Revenue",
         fmt_eur_mm(summary["revenue_target"]),
         fmt_eur_mm(pct5_revenue),
         fmt_eur_mm(rev_at_risk),
         fmt_pct(rev_at_risk / summary["revenue_target"])],
        ["EBITDA",
         fmt_eur_mm(summary["ebitda_target"]),
         fmt_eur_mm(pct5_ebitda),
         fmt_eur_mm(ebitda_at_risk),
         fmt_pct(ebitda_at_risk / summary["ebitda_target"])],
        ["EBIT",
         fmt_eur_mm(summary["ebit_target"]),
         fmt_eur_mm(pct5_ebit),
         fmt_eur_mm(ebit_at_risk),
         fmt_pct(ebit_at_risk / summary["ebit_target"])],
        ["Operating CF (CFaR)",
         fmt_eur_mm(summary["opcf_target"]),
         fmt_eur_mm(pct5_opcf),
         fmt_eur_mm(cfar),
         fmt_pct(summary["cfar_pct_target"])],
    ]
    draw_table(ax_tab, cols, rows,
               col_widths=[0.28, 0.18, 0.18, 0.18, 0.18],
               highlight_row=3)

    return fig


# ═══════════════════════════════════════════════════════════════════════════
# PÁGINA 4 — DESCOMPOSICIÓN POR FACTOR
# ═══════════════════════════════════════════════════════════════════════════
def page_factor_decomposition(company_name: str, year: int,
                              decomposition: pd.DataFrame,
                              page_num: int, total_pages: int) -> plt.Figure:
    fig = plt.figure(figsize=(PAGE_W, PAGE_H))

    draw_page_header(fig,
        title="Descomposición del riesgo por factor",
        subtitle=f"{company_name} · Ejercicio {year}",
        page_num=page_num, total_pages=total_pages)

    # Filtrar solo filas anuales
    annual = decomposition[decomposition["period"] == "Anual"].copy()
    annual = annual.sort_values("std", ascending=True)  # más volatil arriba

    # Calcular % varianza (asumiendo independencia)
    var_total = (annual["std"] ** 2).sum()
    annual["pct_var"] = (annual["std"] ** 2) / var_total

    # Layout: barras a la izquierda, tabla y callout a la derecha
    gs = GridSpec(2, 2, figure=fig,
                  width_ratios=[1.3, 1],
                  height_ratios=[3, 1],
                  top=0.88, bottom=0.06, left=0.07, right=0.96,
                  hspace=0.5, wspace=0.3)

    # ── Barras horizontales ─────────────────────────────────────────────────
    ax = fig.add_subplot(gs[:, 0])

    factors = annual["factor_name"].tolist()
    stds    = annual["std"].tolist()
    pcts    = annual["pct_var"].tolist()

    colors_bars = [BLUE_LIGHT, BLUE_PRIMARY, NAVY][:len(factors)]
    if len(factors) > 3:
        colors_bars = [BLUE_LIGHT] * (len(factors) - 1) + [NAVY]

    bars = ax.barh(factors, stds, color=colors_bars,
                   edgecolor="white", linewidth=1.2)

    # Etiquetas de valor + %
    for bar, std, pct in zip(bars, stds, pcts):
        ax.text(bar.get_width() + max(stds) * 0.01,
                bar.get_y() + bar.get_height() / 2,
                f"σ = {fmt_eur_mm(std)}    ({fmt_pct(pct)} var.)",
                ha="left", va="center",
                fontsize=10, color=NAVY, weight="bold")

    ax.set_xlim(0, max(stds) * 1.4)
    ax.set_xlabel("Desviación estándar del impacto anual (€ mm)")
    ax.set_title("Contribución de cada factor a la varianza del cash flow",
                 loc="left", color=NAVY, pad=10)
    ax.xaxis.set_major_formatter(plt.FuncFormatter(
        lambda x, _: f"{fmt_number(x)}"))
    ax.grid(axis="x", alpha=0.5)

    # ── Tabla detalle (arriba derecha) ──────────────────────────────────────
    ax_tab = fig.add_subplot(gs[0, 1])

    cols = ["Factor", "Línea P&L", "σ (mm)", "% var."]
    rows = []
    for _, r in annual.iterrows():
        rows.append([
            r["factor_code"],
            r["pl_line"],
            fmt_number(r["std"]),
            fmt_pct(r["pct_var"]),
        ])
    draw_table(ax_tab, cols, rows,
               col_widths=[0.25, 0.30, 0.20, 0.25])

    # ── Callout interpretativo (abajo derecha) ──────────────────────────────
    dominant = annual.iloc[-1]  # el de mayor std
    body = (
        f"El factor {dominant['factor_code']} domina con el "
        f"{fmt_pct(dominant['pct_var'])} de la varianza total. Esto refleja "
        f"tanto la magnitud de la exposición como la volatilidad histórica "
        f"del subyacente. Los factores secundarios aportan contribuciones "
        f"marginales individuales pero su inclusión es metodológicamente "
        f"necesaria para preservar la estructura de correlaciones."
    )
    draw_callout(fig, 0.51, 0.08, 0.43, 0.22,
                 title="Factor dominante",
                 body=body)

    return fig


# ═══════════════════════════════════════════════════════════════════════════
# PÁGINA 5 — FAN CHARTS POR FACTOR
# ═══════════════════════════════════════════════════════════════════════════
def page_fan_charts(company_name: str, year: int,
                    quantiles: pd.DataFrame, highlights: pd.DataFrame,
                    page_num: int, total_pages: int) -> plt.Figure:
    fig = plt.figure(figsize=(PAGE_W, PAGE_H))

    draw_page_header(fig,
        title="Evolución temporal de los factores de riesgo",
        subtitle=f"{company_name} · Ejercicio {year}",
        page_num=page_num, total_pages=total_pages)

    factors = quantiles["factor_code"].unique().tolist()
    n_factors = len(factors)

    gs = GridSpec(1, n_factors, figure=fig,
                  top=0.85, bottom=0.10, left=0.06, right=0.97,
                  wspace=0.30)

    for i, factor in enumerate(factors):
        ax = fig.add_subplot(gs[i])

        df_q = quantiles[quantiles["factor_code"] == factor].sort_values("period_order")
        x = df_q["period_order"].values
        labels = df_q["period"].tolist()

        # Bandas
        ax.fill_between(x, df_q["p5"], df_q["p95"],
                        color=BLUE_LIGHT, alpha=0.25, label="5% – 95%")
        ax.fill_between(x, df_q["p25"], df_q["p75"],
                        color=BLUE_PRIMARY, alpha=0.30, label="25% – 75%")

        # Línea media
        ax.plot(x, df_q["mean"],
                color=NAVY, linewidth=2.2, marker="o", markersize=5,
                label="Media")

        # Líneas finas de los escenarios destacados (si hay)
        if highlights is not None and len(highlights) > 0:
            df_h = highlights[highlights["factor_code"] == factor]
            for scen_id, group in df_h.groupby("scenario_id"):
                category = group["rank_category"].iloc[0]
                color = RED if category == "worst" else GREEN
                group_sorted = group.sort_values("period_order")
                ax.plot(group_sorted["period_order"],
                        group_sorted["value"],
                        color=color, linewidth=0.6, alpha=0.4)

        ax.set_xticks(x)
        ax.set_xticklabels(labels, fontsize=8)
        ax.set_title(factor, loc="left", color=NAVY, fontsize=11, pad=8)
        ax.grid(alpha=0.4)
        if i == 0:
            ax.legend(fontsize=8, loc="upper left",
                      framealpha=0.95, edgecolor=GREY_LIGHT)

    # Subtítulo bajo los gráficos
    fig.text(0.5, 0.04,
             "Bandas de incertidumbre simuladas con 10.000 escenarios. "
             "Líneas finas: 5 escenarios peores (rojo) y 5 mejores (verde) "
             "según el Operating Cash Flow resultante.",
             fontsize=8, color=GREY_MEDIUM, style="italic",
             ha="center", va="bottom")

    return fig


# ═══════════════════════════════════════════════════════════════════════════
# PÁGINA 6 — PARÁMETROS DEL EXPOSURE MAP
# ═══════════════════════════════════════════════════════════════════════════
def page_exposure_params(company_name: str, year: int,
                         exposures: list, summary: pd.Series,
                         page_num: int, total_pages: int) -> plt.Figure:
    """
    `exposures` es una lista de Exposure (objeto del exposure_map)
    o un equivalente con los atributos: factor_code, factor_name,
    pl_line, parameters (dict con quantity, unit, hedge_ratio, etc.)
    """
    fig = plt.figure(figsize=(PAGE_W, PAGE_H))

    draw_page_header(fig,
        title="Parámetros del exposure map",
        subtitle=f"{company_name} · Ejercicio {year}",
        page_num=page_num, total_pages=total_pages)

    # Layout: tabla principal arriba, tabla cash flow abajo
    gs = GridSpec(2, 1, figure=fig,
                  height_ratios=[1.4, 1],
                  top=0.88, bottom=0.06, left=0.07, right=0.96,
                  hspace=0.40)

    # ── Tabla parámetros del exposure map ───────────────────────────────────
    ax_exp = fig.add_subplot(gs[0])

    cols = ["Factor", "Línea P&L", "Cantidad", "Cobertura",
            "Coste cobertura", "Distribución estacional"]
    rows = []
    for exp in exposures:
        p = exp.parameters
        qty   = p.get("quantity", "-")
        unit  = p.get("unit", "")
        hedge = p.get("hedge_ratio", 0)
        cost  = p.get("hedge_cost_bps", 0)
        dist  = p.get("quarterly_distribution", [0.25] * 4)

        qty_str = f"{fmt_number(qty)} {unit.replace('million_', 'mm ')}"
        dist_str = " · ".join(f"{int(d*100)}%" for d in dist)

        rows.append([
            exp.factor_code,
            exp.pl_line,
            qty_str,
            fmt_pct(hedge, 0),
            f"{cost} bp",
            dist_str,
        ])

    draw_table(ax_exp, cols, rows,
               col_widths=[0.13, 0.18, 0.22, 0.13, 0.15, 0.19])
    ax_exp.set_title("Parámetros por factor de riesgo",
                     loc="left", color=NAVY, pad=10, fontsize=12, weight="bold")

    # ── Tabla del cash flow target ──────────────────────────────────────────
    ax_cf = fig.add_subplot(gs[1])

    cols2 = ["Concepto", "Importe (€ mm)"]
    rows2 = [
        ["Revenue",                           fmt_number(summary["revenue_target"])],
        ["− Operating costs (cash)",        f"−{fmt_number(summary['opex_target'])}"],
        ["= EBITDA",                          fmt_number(summary["ebitda_target"])],
        ["− D&A",                            f"−{fmt_number(summary['da_target'])}"],
        ["= EBIT",                            fmt_number(summary["ebit_target"])],
        ["− Taxes (EBIT × tax rate)",        f"−{fmt_number(summary['taxes_target'])}"],
        ["= NOPAT",                           fmt_number(summary["nopat_target"])],
        ["+ D&A (devuelto, no-cash)",        f"+{fmt_number(summary['da_target'])}"],
        ["+ ΔWC",                            f"+{fmt_number(summary['wc_change_target'])}"],
        ["= Operating Cash Flow target",      fmt_number(summary["opcf_target"])],
    ]
    draw_table(ax_cf, cols2, rows2,
               col_widths=[0.65, 0.35],
               highlight_row=9)
    ax_cf.set_title("Construcción del Operating Cash Flow target",
                    loc="left", color=NAVY, pad=10, fontsize=12, weight="bold")

    return fig
