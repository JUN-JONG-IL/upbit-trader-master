"""
portfolio/logic package: Business logic facade for the portfolio module.

Re-exports all analysis, optimization, and reporting classes for
convenient access through a unified logic layer.

Exports (analysis):
- AttributionAnalysis
- DrawdownTracker
- PerformanceAnalyzer
- SharpeCalculator

Exports (optimization):
- BlackLittermanOptimizer
- MarkowitzOptimizer
- RLOptimizer

Exports (reporting):
- DailyReport
- PDFGenerator
- WeeklyReport
"""

from ..analysis import (
    AttributionAnalysis,
    DrawdownTracker,
    PerformanceAnalyzer,
    SharpeCalculator,
)
from ..optimization import (
    BlackLittermanOptimizer,
    MarkowitzOptimizer,
    RLOptimizer,
)
from ..reporting import (
    DailyReport,
    PDFGenerator,
    WeeklyReport,
)

__all__ = [
    # analysis
    "AttributionAnalysis",
    "DrawdownTracker",
    "PerformanceAnalyzer",
    "SharpeCalculator",
    # optimization
    "BlackLittermanOptimizer",
    "MarkowitzOptimizer",
    "RLOptimizer",
    # reporting
    "DailyReport",
    "PDFGenerator",
    "WeeklyReport",
]
