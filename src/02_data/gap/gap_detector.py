#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
[SHIM] src/02_data/gap/gap_detector.py

문제 명세에서 언급된 gap_detector.py 경로를 실제 구현(detector.py)으로 연결합니다.

실제 구현: src/02_data/gap/detector.py

CHANGELOG:
- 2026-03-19 | Copilot | gap_detector.py shim 추가 (문제 명세 개선3 참조)
"""
from __future__ import annotations

# detector.py 의 공개 심볼을 모두 re-export 합니다.
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
