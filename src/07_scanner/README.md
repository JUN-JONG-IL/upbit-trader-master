# CHANGELOG
# 2026-03-16 | Copilot | 업그레이드: 07_scanner README v4.0. 버전 통일.
# 2026-03-13 | Copilot | 업그레이드: 07_scanner scanner/ → engine/ 변경.
# 2026-03-06 | Copilot | 생성: 07_scanner README 초안

Version: v4.0
Last Modified: 2026-03-16
References:
  - work_order/1_단계_기관에이전트급_최신_트레이딩_시스템_가이드.md
  - work_order/DB설계.md

# 07_scanner - 종목 스캐너 모듈

## 개요

`07_scanner`는 Upbit 거래소 전체 종목을 실시간으로 스캔하여 사용자가 정의한 조건에 맞는 종목을 자동으로 찾아주는 모듈입니다.

---

## 폴더 구조

```
src/07_scanner/
├── __init__.py                    # 모듈 진입점 (재노출)
├── README.md                      # 이 파일
└── engine/
    ├── __init__.py                # engine 패키지 진입점
    ├── README.md                  # engine 세부 문서
    ├── ui/                        # UI 레이어
    ├── logic/                     # 비즈니스 로직 레이어
    ├── workers/                   # 백그라운드 워커 레이어
    ├── models/                    # 데이터 모델
    ├── indicators/                # 기술 지표
    ├── patterns/                  # 패턴 인식
    ├── tests/                     # 단위 테스트
    └── docs/                      # 추가 문서
```

---

## 주요 기능

- **실시간 스캐닝**: 237개+ 종목 동시 스캔 (병렬 처리)
- **기술적 지표**: MA, EMA, RSI, MACD, Bollinger Bands, Stochastic, ATR, OBV
- **차트 패턴**: 골든크로스, 데드크로스, Doji, Hammer, 삼각수렴 등
- **프리셋 시스템**: 사용자 정의 조건 저장/로드 (기본: 기본/단타용/스윙용)
- **후처리 필터**: 가격/시간/블랙리스트 필터

---

## 빠른 시작

```python
from src._07_scanner import ScannerEngine, ScannerWorker

# 직접 실행
import asyncio
engine = ScannerEngine()
results = asyncio.run(engine.scan(settings))
engine.cleanup()

# PyQt5 워커로 실행
worker = ScannerWorker(settings)
worker.scan_finished.connect(on_results)
worker.start()
```

---

## 테스트 실행

```bash
pytest src/07_scanner/engine/tests/ -v
```

---

## 의존성

- `src/01_core/` : 설정 관리, 이벤트 버스 (스캔 결과 알림 발행)
- `src/data_01/timescale/` : OHLCV 캔들 데이터
- `src/data_01/redis/` : 스캔 결과 캐시
- `src/13_compute/` : 지표 계산 엔진 (O(1) 증분 계산)
- PyQt5 : UI 위젯 (.ui 파일 포함)
- pandas, numpy : 데이터 처리

## 참고 문서

- [`engine/docs/ARCHITECTURE.md`](engine/docs/ARCHITECTURE.md) — 스캐너 아키텍처 설명
- [`engine/docs/API.md`](engine/docs/API.md) — API 레퍼런스
- [`engine/docs/EXAMPLES.md`](engine/docs/EXAMPLES.md) — 사용 예제
- [`work_order/5_단계_Scanner_Search_엔진.md`](../../work_order/5_단계_Scanner_Search_엔진.md)
- [`work_order/1_단계_기관에이전트급_최신_트레이딩_시스템_가이드.md`](../../work_order/1_단계_기관에이전트급_최신_트레이딩_시스템_가이드.md)
