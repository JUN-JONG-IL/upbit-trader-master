# src/13_compute — 계산 엔진

## 개요

GUI와 분리된 전용 계산 프로세스 모듈입니다. 캔들 집계, 지표 증분 계산(O(1) 복잡도), 스캐너 실행을 담당합니다.

`backup/compute/` 디렉토리에서 핵심 파일들을 통합하였습니다.

## 디렉토리 구조

```
src/13_compute/
├── __init__.py            # 패키지 진입점 (ComputeProcess re-export)
├── README.md              # 이 파일
├── engine/                # 핵심 계산 엔진
│   ├── __init__.py
│   ├── README.md
│   ├── compute_main.py    # 계산 프로세스 메인 (backup/compute에서 통합)
│   ├── candle_aggregator.py  # 캔들 집계기
│   ├── indicator_engine.py   # 지표 계산 엔진
│   └── scanner_executor.py   # 스캐너 실행기
├── aggregation/           # 데이터 집계 (틱→초→분→일 롤업)
│   ├── __init__.py
│   └── README.md
└── workers/               # 백그라운드 계산 워커
    ├── __init__.py
    └── README.md
```

## 하위 모듈 설명

### engine/ — 핵심 계산 엔진

캔들 집계, 지표 계산, 스캐너 실행의 핵심 로직을 포함합니다.

**통합 내역**: `backup/compute/` → `src/13_compute/engine/`

**주요 클래스**:
- `ComputeProcess` : 계산 프로세스 메인 (GUI 분리 아키텍처)
- `CandleAggregator` : 틱/초/분/일/주/월/년 캔들 집계
- `IndicatorEngine` : O(1) 증분 계산 기반 지표 엔진
- `ScannerExecutor` : 스캐너 조건 실행기

### aggregation/ — 데이터 집계

틱 데이터를 상위 시간 단위 캔들로 롤업하는 집계 로직입니다.

**주요 클래스**:
- `TickAggregator` : 틱 → 초 단위 캔들 변환
- `OHLCVAggregator` : OHLCV 상위 단위 롤업
- `VolumeAggregator` : 거래량 집계

### workers/ — 백그라운드 계산 워커

백그라운드에서 지속적으로 계산 작업을 처리하는 워커 클래스입니다.

**주요 클래스**:
- `ComputeWorker` : 계산 프로세스 백그라운드 워커
- `AggregationWorker` : 집계 작업 워커
- `SchedulerWorker` : 주기적 계산 스케줄러

## 사용 예시

```python
from src.13_compute import ComputeProcess

process = ComputeProcess()
process.start()
```

## 의존성

- `src/01_core/` : 기본 설정, 이벤트 버스
- `src/02_data/` : TimescaleDB, Redis (집계 데이터 저장/조회)
- `src/07_scanner/` : 스캐너 조건 DSL

## 참고 문서

- [`work_order/4_단계_Compute_프로세스_데이터_집계.md`](../../work_order/4_단계_Compute_프로세스_데이터_집계.md)
- [`work_order/DB설계.md`](../../work_order/DB설계.md) — TimescaleDB 집계 테이블 스키마
- [`work_order/1_단계_기관에이전트급_최신_트레이딩_시스템_가이드.md`](../../work_order/1_단계_기관에이전트급_최신_트레이딩_시스템_가이드.md)
