"""
exposure_map.py
═══════════════════════════════════════════════════════════════════════════
Parser y validador de archivos YAML de Exposure Map (v3).

Modelo: Operating CF = Revenue - Operating Costs - Taxes - ΔWC
Cada exposición se mapea a una línea concreta de la P&L.
"""
import yaml
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional


# ─────────────────────────────────────────────────────────────────────────
# Líneas válidas de la P&L
# ─────────────────────────────────────────────────────────────────────────
VALID_PL_LINES = {"revenue", "operating_costs", "taxes", "wc_change"}
VALID_FUNCTION_TYPES = {"linear", "stepped", "econometric"}


# ─────────────────────────────────────────────────────────────────────────
# Estructura de datos
# ─────────────────────────────────────────────────────────────────────────
@dataclass
class Exposure:
    factor_code:   str
    factor_name:   str
    pl_line:       str          # revenue | operating_costs | taxes | wc_change
    function_type: str
    parameters:    dict
    source:        str = ""


@dataclass
class CashFlowTarget:
    revenue:                   float
    operating_costs:           float
    depreciation_amortization: float
    taxes:                     float
    wc_change:                 float

    @property
    def ebitda(self) -> float:
        """EBITDA = Revenue - Operating costs (cash, sin D&A)."""
        return self.revenue - self.operating_costs

    @property
    def ebit(self) -> float:
        """EBIT = EBITDA - D&A."""
        return self.ebitda - self.depreciation_amortization

    @property
    def nopat(self) -> float:
        """NOPAT = EBIT - Taxes."""
        return self.ebit - self.taxes

    @property
    def operating_cf(self) -> float:
        """Operating CF = NOPAT + D&A + ΔWC.

        La D&A se devuelve porque no es cash. Su único efecto neto sobre
        el cash flow es indirecto, vía la reducción de impuestos pagados.
        """
        return self.nopat + self.depreciation_amortization + self.wc_change


@dataclass
class ExposureMap:
    company_code:        str
    company_name:        str
    functional_currency: str
    reporting_period:    int
    horizon_quarters:    int
    tax_rate:            float
    cash_flow_target:    CashFlowTarget
    exposures:           list
    simulation_config:   dict

    @classmethod
    def from_yaml(cls, path) -> "ExposureMap":
        with open(path, "r", encoding="utf-8") as f:
            raw = yaml.safe_load(f)
        return cls._parse(raw)

    @classmethod
    def _parse(cls, raw: dict) -> "ExposureMap":
        validate_schema(raw)

        cf = raw["cash_flow_target"]
        target = CashFlowTarget(
            revenue                   = cf["revenue"],
            operating_costs           = cf["operating_costs"],
            depreciation_amortization = cf["depreciation_amortization"],
            taxes                     = cf["taxes"],
            wc_change                 = cf["wc_change"],
        )

        return cls(
            company_code        = raw["company"]["code"],
            company_name        = raw["company"]["name"],
            functional_currency = raw["company"]["functional_currency"],
            reporting_period    = raw["company"]["reporting_period"],
            horizon_quarters    = raw["company"]["horizon_quarters"],
            tax_rate            = raw["company"]["tax_rate"],
            cash_flow_target    = target,
            exposures           = [Exposure(**e) for e in raw["exposures"]],
            simulation_config   = raw["simulation"],
        )

    def factor_codes(self) -> list:
        return [exp.factor_code for exp in self.exposures]

    def get_exposure(self, factor_code: str) -> Optional[Exposure]:
        for exp in self.exposures:
            if exp.factor_code == factor_code:
                return exp
        return None

    def exposures_for_line(self, pl_line: str) -> list:
        return [exp for exp in self.exposures if exp.pl_line == pl_line]

    def summary(self) -> str:
        cf = self.cash_flow_target
        lines = []
        lines.append(f"Empresa       : {self.company_name} ({self.company_code})")
        lines.append(f"Periodo       : {self.reporting_period}")
        lines.append(f"Moneda        : {self.functional_currency}")
        lines.append(f"Horizonte     : {self.horizon_quarters} trimestres")
        lines.append(f"Tax rate      : {self.tax_rate:.1%}")
        lines.append(f"")
        lines.append(f"Cash flow target (mm {self.functional_currency}):")
        lines.append(f"  Revenue              {cf.revenue:>10,.0f}")
        lines.append(f"  - Operating costs    {cf.operating_costs:>10,.0f}")
        lines.append(f"  = EBITDA             {cf.ebitda:>10,.0f}")
        lines.append(f"  - D&A                {cf.depreciation_amortization:>10,.0f}")
        lines.append(f"  = EBIT               {cf.ebit:>10,.0f}")
        lines.append(f"  - Taxes              {cf.taxes:>10,.0f}")
        lines.append(f"  = NOPAT              {cf.nopat:>10,.0f}")
        lines.append(f"  + D&A (devuelto)     {cf.depreciation_amortization:>10,.0f}")
        lines.append(f"  + WC change          {cf.wc_change:>10,.0f}")
        lines.append(f"  = Operating CF       {cf.operating_cf:>10,.0f}")
        lines.append(f"")
        lines.append(f"Exposiciones  : {len(self.exposures)}")
        for exp in self.exposures:
            params = exp.parameters
            qty  = params.get('quantity', '-')
            unit = params.get('unit', '')
            hr   = params.get('hedge_ratio', '-')
            sign = params.get('sign', '-')
            qty_str = f"{qty:,}" if isinstance(qty, (int, float)) else str(qty)
            lines.append(
                f"  - {exp.factor_code:<10} → {exp.pl_line:<16} "
                f"qty={qty_str} {unit}, hedge={hr}, sign={sign:+d}"
            )
        return "\n".join(lines)


# ═══════════════════════════════════════════════════════════════════════════
# VALIDACIÓN
# ═══════════════════════════════════════════════════════════════════════════
def validate_schema(raw: dict) -> None:
    for key in ["company", "cash_flow_target", "exposures", "simulation"]:
        if key not in raw:
            raise ValueError(f"Falta sección obligatoria: '{key}'")

    # Empresa
    for key in ["code", "name", "functional_currency",
                "reporting_period", "horizon_quarters", "tax_rate"]:
        if key not in raw["company"]:
            raise ValueError(f"company.{key} es obligatorio")

    if not 0 <= raw["company"]["tax_rate"] <= 1:
        raise ValueError(
            f"company.tax_rate debe estar entre 0 y 1 "
            f"(actual: {raw['company']['tax_rate']})"
        )

    # Cash flow target — las 5 líneas son obligatorias
    for line in ["revenue", "operating_costs", "depreciation_amortization",
                 "taxes", "wc_change"]:
        if line not in raw["cash_flow_target"]:
            raise ValueError(f"cash_flow_target.{line} es obligatorio")

    # Exposiciones
    if not raw["exposures"]:
        raise ValueError("Se requiere al menos una exposición")

    factor_codes = [e["factor_code"] for e in raw["exposures"]]
    if len(factor_codes) != len(set(factor_codes)):
        raise ValueError("factor_code duplicados — solo se permite una "
                         "exposición por factor de riesgo")

    horizon = raw["company"]["horizon_quarters"]

    for i, exp in enumerate(raw["exposures"]):
        for key in ["factor_code", "factor_name", "pl_line",
                    "function_type", "parameters"]:
            if key not in exp:
                raise ValueError(f"exposures[{i}].{key} es obligatorio")

        if exp["pl_line"] not in VALID_PL_LINES:
            raise ValueError(
                f"exposures[{i}].pl_line='{exp['pl_line']}' no válido. "
                f"Válidos: {VALID_PL_LINES}"
            )

        if exp["function_type"] not in VALID_FUNCTION_TYPES:
            raise ValueError(
                f"exposures[{i}].function_type='{exp['function_type']}' "
                f"no válido. Válidos: {VALID_FUNCTION_TYPES}"
            )

        validate_function_params(
            exp["function_type"], exp["parameters"], i, horizon
        )


def validate_function_params(function_type: str, params: dict,
                             idx: int, horizon: int) -> None:
    if "quantity" not in params:
        raise ValueError(f"exposures[{idx}].parameters.quantity es obligatorio")

    if "hedge_ratio" not in params:
        raise ValueError(f"exposures[{idx}].parameters.hedge_ratio es obligatorio")

    if not 0 <= params["hedge_ratio"] <= 1:
        raise ValueError(
            f"exposures[{idx}].parameters.hedge_ratio debe estar entre 0 y 1"
        )

    if "sign" not in params:
        raise ValueError(f"exposures[{idx}].parameters.sign es obligatorio")

    if params["sign"] not in [-1, 1]:
        raise ValueError(f"exposures[{idx}].parameters.sign debe ser -1 o 1")

    if "quarterly_distribution" in params:
        dist = params["quarterly_distribution"]
        if len(dist) != horizon:
            raise ValueError(
                f"exposures[{idx}].parameters.quarterly_distribution debe "
                f"tener {horizon} elementos"
            )
        if abs(sum(dist) - 1.0) > 0.001:
            raise ValueError(
                f"exposures[{idx}].parameters.quarterly_distribution debe "
                f"sumar 1.0 (actualmente: {sum(dist):.4f})"
            )

    if function_type == "stepped":
        if "segments" not in params or not params["segments"]:
            raise ValueError(
                f"exposures[{idx}].parameters.segments es obligatorio y no vacío"
            )

    elif function_type == "econometric":
        if "regression" not in params:
            raise ValueError(f"exposures[{idx}].parameters.regression es obligatorio")
        for r in ["independent_variable", "coefficient"]:
            if r not in params["regression"]:
                raise ValueError(
                    f"exposures[{idx}].parameters.regression.{r} es obligatorio"
                )


# ═══════════════════════════════════════════════════════════════════════════
def load_all(directory) -> list:
    directory = Path(directory)
    maps = []
    for yaml_file in sorted(directory.glob("*.yaml")):
        if yaml_file.name.startswith("_"):
            continue
        try:
            em = ExposureMap.from_yaml(yaml_file)
            maps.append(em)
            print(f"  ✓ Cargado: {yaml_file.name}")
        except Exception as e:
            print(f"  ✗ Error en {yaml_file.name}: {e}")
    return maps


if __name__ == "__main__":
    import sys
    path = sys.argv[1] if len(sys.argv) > 1 else "config/exposure_maps/iag_2026.yaml"
    em = ExposureMap.from_yaml(path)
    print(em.summary())
