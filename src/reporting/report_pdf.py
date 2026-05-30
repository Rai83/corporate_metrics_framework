"""
report_pdf.py
═══════════════════════════════════════════════════════════════════════════
Genera el informe PDF de 6 páginas a partir de los CSVs producidos
por cfar.py.

Uso:
  python -m src.report_pdf IAG 2026
  python -m src.report_pdf IAG 2026 --output output/iag_report.pdf
"""
import argparse
from datetime import datetime
from pathlib import Path

import pandas as pd
from matplotlib.backends.backend_pdf import PdfPages

from src.exposure_mappings.exposure_map import ExposureMap
from src.reporting.theme import apply_theme
from src.reporting.pages import (
    page_cover,
    page_distribution,
    page_pl_cascade,
    page_factor_decomposition,
    page_fan_charts,
    page_exposure_params,
)


def load_data(output_dir: str = "output") -> dict:
    """Carga los 6 CSVs generados por cfar.py."""
    base = Path(output_dir)
    return {
        "companies":     pd.read_csv(base / "companies.csv"),
        "summary":       pd.read_csv(base / "cfar_summary.csv"),
        "scenarios":     pd.read_csv(base / "cfar_scenarios.csv"),
        "decomposition": pd.read_csv(base / "cfar_decomposition.csv"),
        "quantiles":     pd.read_csv(base / "factor_quantiles.csv"),
        "highlights":    pd.read_csv(base / "highlight_scenarios.csv"),
    }


def filter_for(data: dict, company_id: str, year: int) -> dict:
    """Filtra todos los DataFrames para una empresa-año concreta."""
    return {
        "company":       data["companies"][
                            data["companies"]["company_id"] == company_id
                         ].iloc[0],
        "summary":       data["summary"][
                            (data["summary"]["company_id"] == company_id) &
                            (data["summary"]["year"] == year)
                         ].iloc[0],
        "scenarios":     data["scenarios"][
                            (data["scenarios"]["company_id"] == company_id) &
                            (data["scenarios"]["year"] == year)
                         ],
        "decomposition": data["decomposition"][
                            (data["decomposition"]["company_id"] == company_id) &
                            (data["decomposition"]["year"] == year)
                         ],
        "quantiles":     data["quantiles"][
                            (data["quantiles"]["company_id"] == company_id) &
                            (data["quantiles"]["year"] == year)
                         ],
        "highlights":    data["highlights"][
                            (data["highlights"]["company_id"] == company_id) &
                            (data["highlights"]["year"] == year)
                         ],
    }


def generate_report(yaml_path: str, output_pdf: str = None,
                    output_dir: str = "output", author: str = "") -> str:
    """
    Genera un PDF de 6 páginas para la empresa-año del exposure map.

    El YAML se carga solo para obtener los parámetros del exposure map
    (página 6). El resto de los datos vienen de los CSVs.
    """
    # Aplicar tema
    apply_theme()

    # Cargar exposure map (para parámetros) y CSVs
    em = ExposureMap.from_yaml(yaml_path)
    data = load_data(output_dir)
    d = filter_for(data, em.company_code, em.reporting_period)

    # Path de salida
    if output_pdf is None:
        output_pdf = (f"{output_dir}/{em.company_code.lower()}_"
                      f"cfar_{em.reporting_period}_report.pdf")

    company_name = em.company_name
    year         = em.reporting_period
    date_str     = datetime.now().strftime("%d de %B de %Y")
    total_pages  = 6

    print(f"Generando informe PDF: {output_pdf}")

    with PdfPages(output_pdf) as pdf:
        # Página 1 — portada
        fig = page_cover(company_name, year, d["summary"],
                         total_pages, author=author, date_str=date_str)
        pdf.savefig(fig, bbox_inches=None)
        print("  ✓ Página 1 — portada")

        # Página 2 — distribución
        fig = page_distribution(company_name, year, d["summary"],
                                d["scenarios"], page_num=2, total_pages=total_pages)
        pdf.savefig(fig, bbox_inches=None)
        print("  ✓ Página 2 — distribución del Operating Cash Flow")

        # Página 3 — cascada P&L
        fig = page_pl_cascade(company_name, year, d["summary"],
                              d["scenarios"], page_num=3, total_pages=total_pages)
        pdf.savefig(fig, bbox_inches=None)
        print("  ✓ Página 3 — cascada de riesgo P&L")

        # Página 4 — descomposición por factor
        fig = page_factor_decomposition(company_name, year, d["decomposition"],
                                        page_num=4, total_pages=total_pages)
        pdf.savefig(fig, bbox_inches=None)
        print("  ✓ Página 4 — descomposición por factor")

        # Página 5 — fan charts
        fig = page_fan_charts(company_name, year, d["quantiles"],
                              d["highlights"],
                              page_num=5, total_pages=total_pages)
        pdf.savefig(fig, bbox_inches=None)
        print("  ✓ Página 5 — fan charts")

        # Página 6 — parámetros del exposure map
        fig = page_exposure_params(company_name, year, em.exposures,
                                   d["summary"],
                                   page_num=6, total_pages=total_pages)
        pdf.savefig(fig, bbox_inches=None)
        print("  ✓ Página 6 — parámetros del exposure map")

        # Metadatos del PDF
        info = pdf.infodict()
        info["Title"]    = f"CFaR Report — {company_name} {year}"
        info["Author"]   = author or "TFM CorporateMetrics"
        info["Subject"]  = "Cash Flow at Risk analysis"
        info["Keywords"] = "CFaR, CorporateMetrics, risk analysis"

    print(f"\nPDF generado: {output_pdf}")
    return output_pdf


# ═══════════════════════════════════════════════════════════════════════════
# CLI
# ═══════════════════════════════════════════════════════════════════════════
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Generar informe CFaR en PDF")
    parser.add_argument("yaml_path", help="Path del exposure map YAML")
    parser.add_argument("--output", "-o", default=None,
                        help="Path del PDF de salida")
    parser.add_argument("--output-dir", default="output",
                        help="Directorio donde están los CSVs (default: output)")
    parser.add_argument("--author", default="",
                        help="Nombre del autor para la portada")
    args = parser.parse_args()

    generate_report(args.yaml_path, args.output, args.output_dir, args.author)

    # yaml_path = "C:\\Users\\Usuario\\PycharmProjects\\corporate_metrics\\src\\exposure_mappings\\iag_2026.yaml"
    # output = "C:\\Users\\Usuario\\PycharmProjects\\corporate_metrics\\src\\exposure_mappings\\output"
    # output_dir = "C:\\Users\\Usuario\\PycharmProjects\\corporate_metrics\\src\\exposure_mappings\\output"
    # author = "Rai"

    # generate_report(yaml_path, output, output_dir, author)
