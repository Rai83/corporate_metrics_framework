"""
components.py
═══════════════════════════════════════════════════════════════════════════
Componentes visuales reutilizables del informe PDF.
Cada función dibuja sobre un eje (ax) que ya viene configurado.
"""
import matplotlib.patches as patches
import numpy as np
from .theme import (
    BLACK, NAVY, BLUE_PRIMARY, BLUE_LIGHT, BLUE_PALE,
    GREY_DARK, GREY_MEDIUM, GREY_LIGHT, GREY_PALE,
    RED, GREEN, AMBER,
)


# ═══════════════════════════════════════════════════════════════════════════
# CABECERA DE PÁGINA
# ═══════════════════════════════════════════════════════════════════════════
def draw_page_header(fig, title: str, subtitle: str = "",
                     page_num: int = None, total_pages: int = None):
    """Cabecera estándar de cada página — banda superior con título."""
    # Banda decorativa superior
    fig.patches.append(
        patches.Rectangle(
            (0, 0.94), 1, 0.06,
            transform=fig.transFigure,
            facecolor=NAVY, edgecolor="none", zorder=1
        )
    )
    # Título principal en blanco
    fig.text(0.04, 0.97, title,
             fontsize=16, color="white", weight="bold",
             ha="left", va="center", zorder=2)
    # Subtítulo a la derecha
    if subtitle:
        fig.text(0.96, 0.97, subtitle,
                 fontsize=10, color=BLUE_PALE,
                 ha="right", va="center", zorder=2,
                 style="italic")
    # Número de página
    if page_num is not None and total_pages is not None:
        fig.text(0.96, 0.02, f"{page_num} / {total_pages}",
                 fontsize=8, color=GREY_MEDIUM,
                 ha="right", va="bottom")


def draw_page_footer(fig, left_text: str = "", right_text: str = ""):
    """Pie de página discreto."""
    fig.text(0.04, 0.02, left_text,
             fontsize=8, color=GREY_MEDIUM, ha="left", va="bottom")
    if right_text:
        fig.text(0.5, 0.02, right_text,
                 fontsize=8, color=GREY_MEDIUM, ha="center", va="bottom")


# ═══════════════════════════════════════════════════════════════════════════
# KPI CARDS
# ═══════════════════════════════════════════════════════════════════════════
def draw_kpi_card(fig, x: float, y: float, w: float, h: float,
                  label: str, value: str,
                  color: str = NAVY, accent: bool = False,
                  sublabel: str = ""):
    """
    Dibuja una tarjeta de KPI con coordenadas en figura (0..1).

    Si accent=True, usa fondo coloreado en lugar de borde.
    """
    if accent:
        # Tarjeta con fondo de color (para el KPI más importante)
        rect = patches.FancyBboxPatch(
            (x, y), w, h,
            boxstyle="round,pad=0.005,rounding_size=0.008",
            transform=fig.transFigure,
            facecolor=color, edgecolor="none", zorder=1
        )
        fig.patches.append(rect)
        text_color = "white"
        label_color = BLUE_PALE
    else:
        # Tarjeta con borde
        rect = patches.FancyBboxPatch(
            (x, y), w, h,
            boxstyle="round,pad=0.005,rounding_size=0.008",
            transform=fig.transFigure,
            facecolor="white", edgecolor=GREY_LIGHT,
            linewidth=1, zorder=1
        )
        fig.patches.append(rect)
        text_color = NAVY
        label_color = GREY_DARK

    # Label arriba
    fig.text(x + w / 2, y + h - 0.025, label.upper(),
             fontsize=8, color=label_color,
             ha="center", va="top", weight="normal",
             transform=fig.transFigure, zorder=2)

    # Value grande en el centro
    fig.text(x + w / 2, y + h * 0.45, value,
             fontsize=22, color=text_color, weight="bold",
             ha="center", va="center",
             transform=fig.transFigure, zorder=2)

    # Sublabel opcional en la parte inferior
    if sublabel:
        fig.text(x + w / 2, y + 0.020, sublabel,
                 fontsize=8, color=label_color,
                 ha="center", va="bottom", style="italic",
                 transform=fig.transFigure, zorder=2)


# ═══════════════════════════════════════════════════════════════════════════
# CALLOUT BOX (caja interpretativa)
# ═══════════════════════════════════════════════════════════════════════════
def draw_callout(fig, x: float, y: float, w: float, h: float,
                 title: str, body: str,
                 color: str = BLUE_PALE):
    """Caja con titulo y texto interpretativo."""
    rect = patches.FancyBboxPatch(
        (x, y), w, h,
        boxstyle="round,pad=0.005,rounding_size=0.005",
        transform=fig.transFigure,
        facecolor=color, edgecolor="none", zorder=1
    )
    fig.patches.append(rect)

    # Borde lateral izquierdo en navy
    side = patches.Rectangle(
        (x, y), 0.005, h,
        transform=fig.transFigure,
        facecolor=NAVY, edgecolor="none", zorder=2
    )
    fig.patches.append(side)

    fig.text(x + 0.015, y + h - 0.015, title,
             fontsize=10, color=NAVY, weight="bold",
             ha="left", va="top",
             transform=fig.transFigure, zorder=3)

    fig.text(x + 0.015, y + h - 0.04, body,
             fontsize=9, color=BLACK,
             ha="left", va="top", wrap=True,
             transform=fig.transFigure, zorder=3)


# ═══════════════════════════════════════════════════════════════════════════
# TABLAS PROFESIONALES
# ═══════════════════════════════════════════════════════════════════════════
def draw_table(ax, columns: list, rows: list, col_widths: list = None,
               highlight_row: int = None, header_color: str = NAVY):
    """
    Dibuja una tabla profesional sobre un eje.
    `rows` es una lista de listas. `columns` es la cabecera.
    """
    ax.axis("off")

    n_cols = len(columns)
    n_rows = len(rows)

    if col_widths is None:
        col_widths = [1.0 / n_cols] * n_cols
    # Normalizar a suma 1
    col_widths = np.array(col_widths) / sum(col_widths)
    col_x = np.concatenate([[0], np.cumsum(col_widths)])

    row_h = 1.0 / (n_rows + 1)

    # Header
    for i, col in enumerate(columns):
        ax.add_patch(patches.Rectangle(
            (col_x[i], 1 - row_h), col_widths[i], row_h,
            facecolor=header_color, edgecolor="white", linewidth=1
        ))
        ax.text(col_x[i] + col_widths[i] / 2, 1 - row_h / 2, col,
                ha="center", va="center", color="white",
                fontsize=9, weight="bold")

    # Rows
    for r, row in enumerate(rows):
        y = 1 - (r + 2) * row_h
        is_alt = r % 2 == 1
        is_highlight = (highlight_row == r)

        if is_highlight:
            row_bg = BLUE_PALE
            text_w = "bold"
        elif is_alt:
            row_bg = GREY_PALE
            text_w = "normal"
        else:
            row_bg = "white"
            text_w = "normal"

        for c, val in enumerate(row):
            ax.add_patch(patches.Rectangle(
                (col_x[c], y), col_widths[c], row_h,
                facecolor=row_bg, edgecolor=GREY_LIGHT, linewidth=0.5
            ))
            # Primera columna alineada a la izquierda, resto centrada/derecha
            if c == 0:
                ax.text(col_x[c] + 0.01, y + row_h / 2, str(val),
                        ha="left", va="center", color=BLACK,
                        fontsize=9, weight=text_w)
            else:
                ax.text(col_x[c] + col_widths[c] - 0.01, y + row_h / 2, str(val),
                        ha="right", va="center", color=BLACK,
                        fontsize=9, weight=text_w)

    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
