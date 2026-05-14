# engine/ — 핵심 계산 엔진

## 개요

캔들 집계, 지표 계산, 스캐너 실행을 담당하는 핵심 계산 엔진입니다.

`backup/compute/` 디렉토리에서 통합된 파일들이 포함됩니다.

## 주요 파일

| 파일 | 역할 |
|---|---|
| `compute_main.py` | 계산 프로세스 메인 진입점 (GUI 분리 아키텍처) |
| `candle_aggregator.py` | 캔들 데이터 집계 (틱/초/분/일/주/월/년) |
| `indicator_engine.py` | 지표 계산 엔진 (O(1) 증분 계산) |
| `scanner_executor.py` | 스캐너 조건 실행기 |

## 사용 예시

```python
from src.13_compute.engine import ComputeProcess

process = ComputeProcess()
process.start()
```

## 통합 내역

- `backup/compute/compute_main.py` → `src/13_compute/engine/compute_main.py`
- `backup/compute/candle_aggregator.py` → `src/13_compute/engine/candle_aggregator.py`
- `backup/compute/indicator_engine.py` → `src/13_compute/engine/indicator_engine.py`
- `backup/compute/scanner_executor.py` → `src/13_compute/engine/scanner_executor.py`
