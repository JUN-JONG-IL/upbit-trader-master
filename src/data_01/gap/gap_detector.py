#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
[SHIM] src/data_01/gap/gap_detector.py

문제 명세?�서 ?�급??gap_detector.py 경로�??�제 구현(detector.py)?�로 ?�결?�니??

?�제 구현: src/data_01/gap/detector.py

CHANGELOG:
- 2026-03-19 | Copilot | gap_detector.py shim 추�? (문제 명세 개선3 참조)
"""
from __future__ import annotations

# detector.py ??공개 ?�볼??모두 re-export ?�니??
from .detector import (  # noqa: F401
    GapDetector,
    HOT_SYMBOLS,
    GAP_PRIORITY_HIGH,
    GAP_PRIORITY_MEDIUM,
    GAP_PRIORITY_LOW,
)

__all__ = [
    "GapDetector",
    "HOT_SYMBOLS",
    "GAP_PRIORITY_HIGH",
    "GAP_PRIORITY_MEDIUM",
    "GAP_PRIORITY_LOW",
]

