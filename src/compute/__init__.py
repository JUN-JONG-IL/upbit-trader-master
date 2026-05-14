"""
계산 엔진 모듈

[목적]
GUI와 분리된 전용 계산 프로세스로, 캔들 집계, 지표 계산, 스캐너 실행을 담당합니다.

[구조]
- engine/     : 핵심 계산 엔진 (캔들 집계, 지표 계산, 스캐너 실행)
- aggregation/ : 데이터 집계 (틱→초→분→일→주→월 롤업)
- workers/     : 백그라운드 계산 워커

[주요 컴포넌트]
- ComputeProcess     : 계산 프로세스 메인 (backup/compute에서 통합)
- CandleAggregator   : 캔들 집계기
- IndicatorEngine    : 지표 계산 엔진
- ScannerExecutor    : 스캐너 실행기

[통합 내역]
- backup/compute/ → src/compute/engine/ (ComputeProcess, CandleAggregator, IndicatorEngine, ScannerExecutor)
"""
from .engine import ComputeProcess

__all__ = ['ComputeProcess']
