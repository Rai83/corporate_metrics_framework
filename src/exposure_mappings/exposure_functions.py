"""
exposure_functions.py
═══════════════════════════════════════════════════════════════════════════
Funciones de exposición — formulación física trimestral.

Las funciones reciben:
  - factor_simulated: precio en un trimestre concreto (shape: n_scenarios)
  - spot:             precio de referencia (target = spot)
  - quantity_q:       cantidad física consumida/recibida en ese trimestre
  - hedge_ratio:      porcentaje cubierto
  - sign:             +1 (ingreso) o -1 (coste)

Devuelven el impacto en cash flow expresado en moneda funcional.
"""
import numpy as np


# ═══════════════════════════════════════════════════════════════════════════
# 1. LINEAR
# ═══════════════════════════════════════════════════════════════════════════
def apply_linear(factor_simulated: np.ndarray,
                 spot:             float,
                 quantity_q:       float,
                 hedge_ratio:      float,
                 sign:             int,
                 inverse_rate:     bool = False,
                 **kwargs) -> np.ndarray:
    """
    impacto = sign × cantidad_Q × (1 - cobertura) × Δprecio_efectivo

    Donde Δprecio_efectivo es:
      - Si inverse_rate=False: precio_simulado - spot
        (la cantidad está en unidades del numerador del precio)
      - Si inverse_rate=True:  1/precio_simulado - 1/spot
        (la cantidad está en unidades del denominador del precio)

    Casos típicos:
      Coste de combustible:
        cantidad = galones, precio = USD/galón → inverse_rate=False, sign=-1
        El resultado está en USD; se convierte a moneda funcional fuera.

      Déficit USD (empresa en EUR):
        cantidad = USD, precio = EUR/USD → inverse_rate=True, sign=-1
        Para convertir USD a EUR usamos 1/EUR_USD.

      Superávit GBP (empresa en EUR):
        cantidad = GBP, precio = EUR/GBP → inverse_rate=True, sign=+1
        Para convertir GBP a EUR usamos 1/EUR_GBP.
    """
    if inverse_rate:
        delta_efectivo = 1.0 / factor_simulated - 1.0 / spot
    else:
        delta_efectivo = factor_simulated - spot

    return sign * quantity_q * (1 - hedge_ratio) * delta_efectivo


# ═══════════════════════════════════════════════════════════════════════════
# 2. STEPPED
# ═══════════════════════════════════════════════════════════════════════════
def apply_stepped(factor_simulated: np.ndarray,
                  spot:             float,
                  quantity_q:       float,
                  sign:             int,
                  segments:         list,
                  inverse_rate:     bool = False,
                  **kwargs) -> np.ndarray:
    """
    Cobertura escalonada según el rango de variación porcentual.

    segments: lista con condiciones tipo "delta < -0.20" (donde delta es
              la variación relativa del precio respecto al spot).
    """
    delta_relativo = factor_simulated / spot - 1.0

    hedge = np.zeros_like(delta_relativo)
    for seg in segments:
        condition_str = seg["condition"]
        mask = eval(condition_str, {"__builtins__": {}},
                    {"delta": delta_relativo, "np": np})
        hedge = np.where(mask, seg["hedge_ratio"], hedge)

    if inverse_rate:
        delta_efectivo = 1.0 / factor_simulated - 1.0 / spot
    else:
        delta_efectivo = factor_simulated - spot

    return sign * quantity_q * (1 - hedge) * delta_efectivo


# ═══════════════════════════════════════════════════════════════════════════
# 3. ECONOMETRIC
# ═══════════════════════════════════════════════════════════════════════════
def apply_econometric(factor_simulated: np.ndarray,
                      spot:             float,
                      quantity_q:       float,
                      hedge_ratio:      float,
                      sign:             int,
                      regression:       dict,
                      inverse_rate:     bool = False,
                      **kwargs) -> np.ndarray:
    """
    Aplica una relación econométrica entre el factor observable y el
    precio efectivo que paga/recibe la empresa.

    delta_efectivo_relativo = intercept + coefficient × delta_factor_relativo
    """
    delta_factor = factor_simulated / spot - 1.0
    intercept   = regression.get("intercept", 0.0)
    coefficient = regression["coefficient"]
    delta_efectivo_rel = intercept + coefficient * delta_factor

    delta_absoluto = delta_efectivo_rel * spot   # vuelta a unidades de precio

    return sign * quantity_q * (1 - hedge_ratio) * delta_absoluto


# ═══════════════════════════════════════════════════════════════════════════
# DISPATCHER
# ═══════════════════════════════════════════════════════════════════════════
FUNCTION_DISPATCHER = {
    "linear":      apply_linear,
    "stepped":     apply_stepped,
    "econometric": apply_econometric,
}


def apply_exposure_quarter(factor_simulated_q: np.ndarray,
                           spot:               float,
                           quantity_q:         float,
                           exposure) -> np.ndarray:
    """
    Aplica la función de exposición correspondiente, para un trimestre dado.

    Parámetros:
      factor_simulated_q : precio simulado en el trimestre (n_scenarios,)
      spot               : precio de referencia
      quantity_q         : cantidad física en el trimestre = quantity × dist[t]
      exposure           : objeto Exposure
    """
    func = FUNCTION_DISPATCHER[exposure.function_type]

    # Sustituimos 'quantity' por 'quantity_q' (la del trimestre)
    params = {**exposure.parameters, "quantity_q": quantity_q}

    # Eliminamos parámetros que ya están consumidos en niveles superiores
    for key in ("quantity", "quarterly_distribution",
                "unit", "currency_conversion"):
        params.pop(key, None)

    return func(factor_simulated_q, spot, **params)