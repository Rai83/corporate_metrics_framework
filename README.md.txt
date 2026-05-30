# Corporate Metrics — Cash Flow at Risk

> Python implementation of J.P. Morgan's CorporateMetrics framework for Cash Flow at Risk (CFaR)
> calculation in non-financial companies. Features Monte Carlo simulation with Cholesky correlation,
> P&L decomposition, efficient hedging frontier (1M+ combinations) and automated PDF reporting.
> Case study: International Airlines Group 2026.

[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/)
[![License](https://img.shields.io/badge/license-Apache%202.0-green.svg)](LICENSE)
[![TimescaleDB](https://img.shields.io/badge/database-TimescaleDB-orange.svg)](https://www.timescale.com/)

---

## Overview

CorporateMetrics is a framework originally published by J.P. Morgan (1999) that adapts the
Value at Risk (VaR) methodology to the corporate world. Instead of measuring portfolio losses,
it quantifies the probability distribution of a company's cash flow under different market
scenarios.

This project implements the full framework in Python and applies it to **International Airlines
Group (IAG)** for fiscal year 2026, using only publicly available data from official financial
statements, FRED and Yahoo Finance.

### Key results — IAG 2026

| Metric | Value |
|--------|-------|
| Operating CF target (net) | €4,996M |
| Operating CF simulated mean | €4,972M |
| **CFaR (95% confidence)** | **€1,011M (20.2% of target)** |
| Revenue at Risk | €71M |
| EBITDA at Risk | €1,348M |
| Jet fuel variance contribution | ~99% |

### Efficient hedging frontier

The model evaluates **1,030,301 hedging combinations** (1% grid across 3 factors) and identifies
1,252 Pareto-efficient points. Key finding: IAG could save **€9.1M/year** in hedging costs while
maintaining the same CFaR level by adjusting its FX hedging strategy.

![Efficient Frontier](docs/iag_frontier_2026.png)

---

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│  Layer 1 — Data                                             │
│  FRED (jet fuel) · Yahoo Finance (FX) · IAG Annual Report  │
│  TimescaleDB (historical 2019–2024) · iag_2026.yaml        │
├─────────────────────────────────────────────────────────────┤
│  Layer 2 — Calculation (Python)                             │
│  cfar.py (Monte Carlo · Cholesky · P&L chain)              │
│  frontier.py (efficient frontier · Common Random Numbers)   │
│  exposure_map.py · exposure_functions.py                    │
├─────────────────────────────────────────────────────────────┤
│  Layer 3 — Visualisation                                    │
│  6× CSV (star schema) · PDF report (6 pages)               │
│  Frontier PNG · Power BI compatible                         │
└─────────────────────────────────────────────────────────────┘
```

---

## Project structure

```
corporate_metrics_framework/
├── config/
│   └── exposure_maps/
│       └── iag_2026.yaml          # IAG exposure map configuration
├── src/
│   ├── cfar.py                    # Main CFaR engine
│   ├── frontier.py                # Efficient hedging frontier
│   ├── exposure_map.py            # YAML parser and validator
│   ├── exposure_functions.py      # Exposure functions (linear, stepped)
│   ├── report_pdf.py              # Automated PDF report generator
│   ├── db/
│   │   └── client.py              # TimescaleDB client
│   ├── service/
│   │   └── download.py            # Historical data downloader
│   └── reporting/
│       ├── theme.py               # Visual theme and colours
│       ├── components.py          # Chart components
│       └── pages.py               # PDF pages
├── sql/
│   └── database_setup.sql         # Database schema and indexes
├── output/
│   └── .gitkeep                   # Generated files go here (git-ignored)
├── requirements.txt
├── .env.example
├── .gitignore
├── LICENSE
└── README.md
```

---

## Getting started

### Prerequisites

| Requirement | Version | Notes |
|-------------|---------|-------|
| Python | 3.11+ | Via Python Launcher: `py install 3.11` |
| Docker Desktop | Latest | For TimescaleDB |
| Git | Any | For cloning |

**Minimum hardware for CFaR model:** 8 GB RAM, any modern dual-core CPU.
**Recommended for full frontier (1% grid):** 16 GB RAM, Intel i5 8th gen or equivalent.
Expected runtime on Intel i5-12500H / 16 GB: ~10 minutes for 1,030,301 combinations.

---

### Installation

```bash
# 1. Clone the repository
git clone https://github.com/Rai83/corporate_metrics_framework.git
cd corporate_metrics_framework

# 2. Create and activate virtual environment
py -3.11 -m venv .venv
.venv\Scripts\activate          # Windows
source .venv/bin/activate        # Linux / macOS

# 3. Install dependencies
pip install -r requirements.txt

# 4. Configure environment variables
cp .env.example .env
# Edit .env with your database credentials
```

---

### Database setup

```bash
# 1. Start TimescaleDB container
docker run -d --name timescaledb \
  -p 5432:5432 \
  -e POSTGRES_USER=postgres \
  -e POSTGRES_PASSWORD=your_password \
  -e POSTGRES_DB=corporate_metrics \
  -v timescaledb_data:/var/lib/postgresql/data \
  timescale/timescaledb:latest-pg16

# 2. Create schema and indexes
psql -h localhost -U postgres -d corporate_metrics -f sql/database_setup.sql

# 3. Download historical market data (2019–2024)
# Sources: FRED (jet fuel MJFUELUSGULF) + Yahoo Finance (EUR/USD, EUR/GBP)
python -m src.service.download
```

---

### Running the model

**Calculate CFaR for IAG 2026:**

```bash
python -m src.cfar config/exposure_maps/iag_2026.yaml
```

Output files generated in `output/`:
- `cfar_summary.csv` — KPIs and at-risk metrics
- `cfar_scenarios.csv` — 10,000 individual scenarios
- `cfar_decomposition.csv` — risk breakdown by factor and P&L line
- `factor_quantiles.csv` — quarterly factor percentiles
- `highlight_scenarios.csv` — key scenarios (p5, median, p95)
- `companies.csv` — company metadata
- `iag_cfar_2026.png` — simulated cash flow distribution chart
- `iag_report_2026.pdf` — 6-page automated PDF report

---

**Calculate the efficient hedging frontier:**

```bash
# Fast exploration (11 values per factor = 1,331 combinations, ~5 seconds)
python -m src.frontier config/exposure_maps/iag_2026.yaml --grid 11

# Full resolution (101 values per factor = 1,030,301 combinations, ~10 min)
python -m src.frontier config/exposure_maps/iag_2026.yaml --grid 101
```

| Grid | Combinations | Runtime (i5-12500H) |
|------|-------------|----------------------|
| 11 (10%) | 1,331 | ~5 seconds |
| 21 (5%) | 9,261 | ~30 seconds |
| 51 (2%) | 132,651 | ~3 minutes |
| 101 (1%) | 1,030,301 | ~10 minutes |

Output files:
- `iag_frontier_2026.csv` — all grid points with Pareto efficiency flag
- `iag_frontier_2026.png` — frontier chart with current IAG position

---

## Configuration — Exposure map

The model is configured via a YAML file. To apply the model to a different company, create a
new exposure map — no code changes required.

```yaml
company_code: IAG
company_name: International Airlines Group
reporting_period: 2026
functional_currency: EUR
tax_rate: 0.25

cash_flow_target:
  revenue:                   34306
  operating_costs:           29306
  depreciation_amortization:  2800
  wc_change:                   568

exposures:
  - factor_code: jet_fuel
    pl_line: operating_costs
    function_type: linear
    parameters:
      quantity: 3181             # million gallons
      quarterly_distribution: [0.22, 0.24, 0.30, 0.24]
      hedge_ratio: 0.65
      hedge_cost_bps: 50
      sign: 1
      currency_conversion:
        factor_code: eur_usd
        type: divide

simulation_config:
  n_scenarios: 10000
  horizon_quarters: 4
  confidence_level: 0.95
  seed: 42
  historical_data_window:
    start: 2019-01-01
    end:   2024-12-31
```

---

## Methodology

- **Monte Carlo simulation** — 10,000 scenarios per run
- **Geometric Brownian Motion** — price path generation for each risk factor
- **Cholesky decomposition** — preserves historical correlations between factors
- **P&L decomposition** — revenue → operating costs → EBITDA → EBIT → taxes → NOPAT → operating CF
- **Posture B (Markowitz-consistent)** — hedge cost propagated through P&L chain, capturing
  the tax shield on hedging premiums. CFaR measures residual market risk only.
- **Common Random Numbers** — same Monte Carlo shocks reused across all frontier combinations,
  eliminating noise in comparative analysis and enabling 1M+ evaluations in minutes.

---

## Reproducibility

Results are fully reproducible:
1. **Fixed random seed** — defined in the exposure map (`seed: 42`)
2. **Local data storage** — historical prices stored in TimescaleDB, no external dependency at runtime
3. **Pinned dependencies** — exact versions in `requirements.txt`

---

## Technologies

| Component | Technology |
|-----------|-----------|
| Language | Python 3.11+ |
| Numerical computation | NumPy, pandas |
| Visualisation | matplotlib |
| Database | PostgreSQL + TimescaleDB |
| ORM | SQLAlchemy |
| Configuration | PyYAML |
| Data sources | FRED API, Yahoo Finance (yfinance) |
| Environment | python-dotenv |

---

## Academic context

This project was developed as part of a Master's Thesis in Corporate Finance at
**Barcelona Finance School** (2025–2026).

- **Author:** Rai Paniagua Salvatella
- **Supervisor:** Salvador Torra
- **LinkedIn:** [raimon-paniagua-salvatella](https://www.linkedin.com/in/raimon-paniagua-salvatella/)

**Reference:** J.P. Morgan & Reuters (1999). *CorporateMetrics Technical Document*.
New York: RiskMetrics Group.

---

## Roadmap

- [ ] Asymmetric hedging instruments (options, collars) with Black-Scholes / Garman-Kohlhagen pricing
- [ ] Multi-company analysis and sector benchmarking (Ebro Foods case)
- [ ] Interest rate risk on variable debt
- [ ] Working capital sensitivity to market factors
- [ ] Interactive web interface (Streamlit)
- [ ] Historical backtesting validation

---

## License

Licensed under the **Apache License 2.0** — see [LICENSE](LICENSE) for details.

You are free to use, modify and distribute this software, including for commercial purposes,
provided you include the original copyright notice and attribution.

---

## Contributing

Contributions, issues and feature requests are welcome. Feel free to open an issue or submit
a pull request.