# CHANGELOG
# 2026-03-06 | Copilot | Initial documentation for portfolio sub-module

Version: v1.0
Last Modified: 2026-03-06 | Copilot

# README: src/portfolio/portfolio

## Purpose
The `portfolio` sub-module displays account holdings and provides portfolio analytics,
weight optimization, and reporting for the Upbit trading application.

## Architecture

### Module Structure
```
portfolio/
├── __init__.py          # Exports PortfolioWidget, PortfolioOptimizer
├── README.md            # This file
├── optimizer.py         # PortfolioOptimizer (Markowitz, efficient frontier, risk parity)
├── ui/                  # UI widgets
│   ├── __init__.py
│   ├── widget_portfolio.py     # PortfolioWidget: main portfolio tab widget
│   ├── widget_holding_list.py  # HoldingListWidget: account holdings list
│   ├── widget_detail_holding.py # DetailHoldingWidget: per-coin detail view
│   ├── holding_list.ui         # Qt Designer UI for holding list
│   └── detail_holding_list.ui  # Qt Designer UI for detail view
├── logic/               # Business logic facade
│   └── __init__.py      # Re-exports from analysis, optimization, reporting
├── analysis/            # Portfolio performance analysis
│   ├── __init__.py
│   ├── attribution_analysis.py  # AttributionAnalysis
│   ├── drawdown_tracker.py      # DrawdownTracker
│   ├── performance_analyzer.py  # PerformanceAnalyzer
│   └── sharpe_calculator.py     # SharpeCalculator
├── optimization/        # Portfolio weight optimization
│   ├── __init__.py
│   ├── black_litterman.py       # BlackLittermanOptimizer
│   ├── markowitz_optimizer.py   # MarkowitzOptimizer
│   └── rl_optimizer.py          # RLOptimizer
├── reporting/           # Portfolio reporting
│   ├── __init__.py
│   ├── daily_report.py          # DailyReport
│   ├── pdf_generator.py         # PDFGenerator
│   └── weekly_report.py         # WeeklyReport
└── workers/             # Background workers (placeholder)
    └── __init__.py
```

## Main Classes

| Class | File | Description |
|---|---|---|
| `PortfolioWidget` | `ui/widget_portfolio.py` | Main portfolio tab widget (holdings + detail) |
| `PortfolioOptimizer` | `optimizer.py` | Markowitz, efficient frontier, risk parity |
| `AttributionAnalysis` | `analysis/attribution_analysis.py` | Return attribution analysis |
| `DrawdownTracker` | `analysis/drawdown_tracker.py` | Maximum drawdown tracking |
| `PerformanceAnalyzer` | `analysis/performance_analyzer.py` | Portfolio performance metrics |
| `SharpeCalculator` | `analysis/sharpe_calculator.py` | Sharpe ratio calculation |
| `MarkowitzOptimizer` | `optimization/markowitz_optimizer.py` | Mean-variance optimization |
| `BlackLittermanOptimizer` | `optimization/black_litterman.py` | Black-Litterman model |
| `RLOptimizer` | `optimization/rl_optimizer.py` | Reinforcement learning optimizer |
| `DailyReport` | `reporting/daily_report.py` | Daily portfolio report |
| `WeeklyReport` | `reporting/weekly_report.py` | Weekly portfolio report |
| `PDFGenerator` | `reporting/pdf_generator.py` | PDF report generator |

## Usage

### Import Main Widget
```python
from src._portfolio.portfolio import PortfolioWidget

portfolio = PortfolioWidget()
portfolio.show()
```

### Import Optimizer
```python
from src._portfolio.portfolio import PortfolioOptimizer

optimizer = PortfolioOptimizer(returns_df)
result = optimizer.optimize(method="max_sharpe")
```

### Import via Logic Facade
```python
from src._portfolio.portfolio.logic import (
    PerformanceAnalyzer,
    MarkowitzOptimizer,
    DailyReport,
)
```

## Dependencies
- PyQt5 (for UI widgets)
- scipy (for optimization algorithms)
- numpy, pandas (for data processing)
- reportlab or similar (for PDF generation)
- `static.account` (internal account state)

## Testing
```bash
# Test portfolio widget
python -m src._portfolio.portfolio.ui.widget_portfolio

# Test optimizer
python -m src._portfolio.portfolio.optimizer
```
