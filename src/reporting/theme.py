"""
theme.py
═══════════════════════════════════════════════════════════════════════════
Estilo visual del informe PDF — paleta tipo consultoría profesional.
Todo el resto de módulos importan constantes desde aquí.
"""
import matplotlib as mpl
import matplotlib.pyplot as plt

# ─────────────────────────────────────────────────────────────────────────
# PALETA
# ─────────────────────────────────────────────────────────────────────────
BLACK         = "#2B2B2B"     # texto principal, líneas
NAVY          = "#1F3864"     # color corporativo
BLUE_PRIMARY  = "#4472C4"     # acento principal
BLUE_LIGHT    = "#8FAADC"     # acento secundario
BLUE_PALE     = "#DAE3F3"     # fondos de tabla
GREY_DARK     = "#404040"     # texto secundario
GREY_MEDIUM   = "#767171"     # gridlines, ejes
GREY_LIGHT    = "#D9D9D9"     # bordes
GREY_PALE     = "#F2F2F2"     # fondos alternos
RED           = "#C00000"     # zona de riesgo
GREEN         = "#4F7942"     # target
AMBER         = "#BF9000"     # advertencias suaves

# ─────────────────────────────────────────────────────────────────────────
# DIMENSIONES (16:9 horizontal)
# ─────────────────────────────────────────────────────────────────────────
PAGE_W = 16    # inches
PAGE_H = 9

# ─────────────────────────────────────────────────────────────────────────
# CONFIGURACIÓN GLOBAL DE MATPLOTLIB
# ─────────────────────────────────────────────────────────────────────────
def apply_theme():
    """Aplica el estilo McKinsey-like a matplotlib globalmente."""
    mpl.rcParams.update({
        # Fuentes
        "font.family": ["Arial", "DejaVu Sans", "Helvetica"],
        "font.size":        10,
        "axes.titlesize":   12,
        "axes.titleweight": "bold",
        "axes.labelsize":   10,
        "xtick.labelsize":  9,
        "ytick.labelsize":  9,
        "legend.fontsize":  9,

        # Colores
        "axes.edgecolor":   GREY_MEDIUM,
        "axes.labelcolor":  BLACK,
        "xtick.color":      GREY_DARK,
        "ytick.color":      GREY_DARK,
        "text.color":       BLACK,

        # Bordes y grid
        "axes.spines.top":   False,
        "axes.spines.right": False,
        "axes.linewidth":    0.8,
        "grid.color":        GREY_LIGHT,
        "grid.linestyle":    "--",
        "grid.linewidth":    0.5,
        "grid.alpha":        0.7,

        # Figuras
        "figure.facecolor":  "white",
        "axes.facecolor":    "white",
        "savefig.facecolor": "white",
        "savefig.dpi":       150,
    })


# ─────────────────────────────────────────────────────────────────────────
# HELPERS DE FORMATO
# ─────────────────────────────────────────────────────────────────────────
def fmt_eur_mm(value: float, decimals: int = 0) -> str:
    """Formatea un valor en millones de EUR. Ej: 5018 → '€ 5.018 mm'."""
    fmt = f"{{:,.{decimals}f}}".format(value)
    fmt = fmt.replace(",", "X").replace(".", ",").replace("X", ".")
    return f"€ {fmt} mm"


def fmt_pct(value: float, decimals: int = 1) -> str:
    """Formatea un valor como porcentaje. Ej: 0.206 → '20,6%'."""
    fmt = f"{{:.{decimals}f}}".format(value * 100)
    return fmt.replace(".", ",") + "%"


def fmt_number(value: float, decimals: int = 0) -> str:
    """Formatea un número con separador de miles europeo. Ej: 5018 → '5.018'."""
    fmt = f"{{:,.{decimals}f}}".format(value)
    return fmt.replace(",", "X").replace(".", ",").replace("X", ".")
