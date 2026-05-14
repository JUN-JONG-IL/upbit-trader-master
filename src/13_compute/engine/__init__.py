"""
핵심 계산 엔진

[목적]
캔들 집계, 지표 계산, 스캐너 실행 등 핵심 계산 로직을 제공합니다.
backup/compute/ 디렉토리에서 통합된 파일들이 포함됩니다.

[주요 파일]
- compute_main.py       : 계산 프로세스 메인 진입점
- candle_aggregator.py  : 캔들 데이터 집계기
- indicator_engine.py   : 지표 계산 엔진 (O(1) 증분 계산)
- scanner_executor.py   : 스캐너 실행기

[통합 내역]
- backup/compute/compute_main.py       → src/13_compute/engine/
- backup/compute/candle_aggregator.py  → src/13_compute/engine/
- backup/compute/indicator_engine.py   → src/13_compute/engine/
- backup/compute/scanner_executor.py   → src/13_compute/engine/
"""
from .compute_main import ComputeProcess

__all__ = ['ComputeProcess']
